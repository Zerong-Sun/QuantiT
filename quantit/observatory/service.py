"""Independent observation worker. Never imports brokers or execution strategies."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
import logging
import threading

from .catalog import NEWS_SOURCES, SERIES
from .factors import local_ic
from .sources import download_dataset, get_bytes, parse_news, parse_series
from .store import archive, atomic, default_root, failed_series, read, save_series, utcnow

LOG = logging.getLogger(__name__)


class ObservatoryWorker:
    def __init__(self, root=None):
        self.root = root or default_root()
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.lock = threading.Lock()
        self.thread = None
        self.force = False

    def state(self, phase, **extra):
        atomic(self.root / "service.json", {"state": phase, "heartbeat": utcnow().isoformat(), **extra})

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, name="macro-observatory", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=2)

    def request_refresh(self):
        if not self.thread or not self.thread.is_alive():
            return False
        self.force = True
        self.wake.set()
        return True

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                forced, self.force = self.force, False
                self.refresh(force=forced)
            except Exception:
                LOG.exception("Observatory refresh failed")
                self.state("error", error="本轮刷新异常，保留已缓存数据")
            self.wake.wait(60)
            self.wake.clear()
        self.state("stopped")

    def refresh(self, force=False):
        if not self.lock.acquire(blocking=False):
            return
        try:
            schedule = read(self.root / "schedule.json", {})
            now = utcnow()
            from datetime import datetime

            def due(key, hours):
                prior = schedule.get(key)
                return force or not prior or now - datetime.fromisoformat(prior) >= timedelta(hours=hours)

            macro_due, news_due = due("macro", 6), due("news", .25)
            if not macro_due and not news_due:
                self.state("waiting")
                return
            self.state("refreshing")
            if macro_due:
                groups = {}
                for key, meta in SERIES.items():
                    if meta["dataset"] != "local":
                        groups.setdefault((meta["provider"], meta["dataset"]), []).append(key)
                with ThreadPoolExecutor(max_workers=4) as executor:
                    jobs = {executor.submit(download_dataset, *group): keys for group, keys in groups.items()}
                    for job in as_completed(jobs):
                        keys = jobs[job]
                        try:
                            payload, extension, origin = job.result()
                            evidence = {**archive(self.root, payload, extension), **origin}
                            for key in keys:
                                try:
                                    save_series(self.root, key, parse_series(SERIES[key], payload), evidence)
                                except Exception as exc:
                                    failed_series(self.root, key, exc)
                        except Exception as exc:
                            for key in keys:
                                failed_series(self.root, key, exc)
                        self.state("refreshing")
                try:
                    for key, result in local_ic().items():
                        if key in SERIES:
                            if isinstance(result, Exception):
                                failed_series(self.root, key, result)
                            else:
                                values, evidence = result
                                try:
                                    save_series(self.root, key, values, evidence)
                                except Exception as exc:
                                    failed_series(self.root, key, exc)
                except Exception as exc:
                    for key, meta in SERIES.items():
                        if meta["dataset"] == "local":
                            failed_series(self.root, key, exc)
                schedule["macro"] = now.isoformat()
            if news_due:
                previous = read(self.root / "news.json", {"articles": [], "sources": {}})
                articles = {x["id"]: x for x in previous["articles"]}
                states = previous.get("sources", {})
                for source_id, source in NEWS_SOURCES.items():
                    try:
                        payload = get_bytes(source["url"])
                        evidence = archive(self.root, payload, "xml")
                        for article in parse_news(payload, source_id, source):
                            old = articles.get(article["id"], {})
                            articles[article["id"]] = {**article, "first_seen": old.get("first_seen", now.isoformat())}
                        states[source_id] = {**source, "fetched_at": utcnow().isoformat(),
                                             "error": None, "evidence": evidence}
                    except Exception as exc:
                        states[source_id] = {**states.get(source_id, source), "error": str(exc)[:350]}
                    self.state("refreshing")
                ordered = sorted(articles.values(), key=lambda x: x.get("published_at") or "", reverse=True)
                atomic(self.root / "news.json", {"articles": ordered[:5000], "sources": states,
                                                 "updated_at": utcnow().isoformat()})
                schedule["news"] = now.isoformat()
            atomic(self.root / "schedule.json", schedule)
            self.state("waiting")
        finally:
            self.lock.release()
