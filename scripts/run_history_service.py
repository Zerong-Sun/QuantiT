#!/usr/bin/env python3
"""Continue isolated paper histories after market closes; no brokerage connection.

Run with the research Python (.venv311). Price downloads and model predictions
are versioned. Execution is delegated to the project's paper Python (.venv).
An unsuccessful book resumes its last committed day on the next attempt.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from quantit.paper.history_data import atomic_json, download, request_symbols

STOP = threading.Event()


def close_key(now: datetime) -> str:
    """Wait an hour after each regular close; weekends do not create sessions.

    This key schedules downloads, not market sessions. Reference bar calendars
    in the executor handle venue-specific holidays and never invent a trade day.
    """
    parts = []
    for venue, zone, hour in [('us','America/New_York',17), ('hk','Asia/Hong_Kong',17), ('cn','Asia/Shanghai',16)]:
        local = now.astimezone(ZoneInfo(zone))
        day = local.date() - timedelta(days=int(local.hour < hour))
        while day.weekday() >= 5:
            day -= timedelta(days=1)
        parts.append(f'{venue}{day}')
    return '_'.join(parts)


def status(root: Path, state: str, **kwargs):
    atomic_json(root/'service.json', {'state':state, 'heartbeat':datetime.now(timezone.utc).isoformat(),
                                     'pid':os.getpid(), **kwargs})


def command(root: Path, argv: list[str], stage: str):
    status(root, 'running', stage=stage)
    with (root/'worker.log').open('ab') as log:
        child = subprocess.Popen(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        started = datetime.now(timezone.utc)
        try:
            while child.poll() is None:
                if STOP.wait(30):
                    raise InterruptedError('Service stopping; current day will retry')
                status(root, 'running', stage=stage)
                if (datetime.now(timezone.utc)-started).total_seconds() > 7200:
                    raise TimeoutError(f'{stage} exceeded two hours')
            if child.returncode:
                raise RuntimeError(f'{stage} failed (exit {child.returncode}); see {root / "worker.log"}')
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()


def cycle(root: Path, config: dict, *, now: datetime | None = None):
    import pandas as pd

    now = now or datetime.now(timezone.utc)
    key = close_key(now)
    state_path = root/'cycle.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if state.get('completed_key') == key:
        status(root,'waiting',completed_key=key,last_completed=state.get('last_completed'))
        return
    end = str(now.astimezone(ZoneInfo('Asia/Shanghai')).date())
    # Retries get new snapshots, so a delayed provider correction cannot rewrite
    # the historical evidence used by already committed days.
    version = now.strftime('%Y%m%dT%H%M%SZ')
    feed = root/'feeds'/version
    status(root,'running',stage='下载收盘行情')
    panel = pd.read_parquet(Path(config['source_data'])/'panel.parquet')
    feed_info = download(feed,request_symbols(panel),config['start'],end)
    signals = Path(state.get('signals',config['signals']))
    model_issue = None
    cn_info = feed_info['symbols'].get('510300.SS',{})
    cn_end = cn_info.get('last')
    # The download may include a not-yet-closed CN bar when the US closes.
    cn_cutoff = next(x[2:] for x in key.split('_') if x.startswith('cn'))
    if cn_end and cn_end > cn_cutoff:
        frame = pd.read_parquet(feed/cn_info['file'])
        eligible = frame.index[frame.index <= pd.Timestamp(cn_cutoff)]
        cn_end = str(eligible[-1].date()) if len(eligible) else None
    old_asof = json.loads((signals/'manifest.json').read_text())['data_asof']
    if cn_end and cn_end > old_asof:
        destination = root/'model-data'/version
        new_signals = root/'signals'/version
        try:
            command(root,[sys.executable,'-m','closeloop.data.refresh','--source',config['source_data'],
                          '--destination',str(destination),'--end',cn_end], '更新固定股票池特征数据')
            command(root,[sys.executable,'-m','closeloop.model.history_signals','--experiment',config['experiment'],
                          '--data-dir',str(destination),'--destination',str(new_signals),'--start',config['start']],
                    '用冻结模型生成新信号')
            signals = new_signals
        except (RuntimeError,TimeoutError) as exc:
            model_issue = str(exc)
            logging.exception('Model refresh failed; existing rule books may continue')
    command(root,[str(ROOT/'.venv/bin/python'),'-m','quantit.paper.history','--root',str(root),
                  '--feed',str(feed),'--signals',str(signals),'--start',config['start'],'--end',end],
            '逐日续跑各策略')
    report = json.loads((root/'report.json').read_text())
    failures = [s['id'] for s in report['strategies'] if s['status']=='blocked']
    missing = [s for s,r in feed_info['symbols'].items() if 'error' in r]
    if failures or missing or model_issue:
        # Do not mark successful: the next hourly pass retries without replaying
        # any already committed days or silently switching the trained model.
        atomic_json(state_path,{**state,'signals':str(signals)})
        raise RuntimeError(f'待重试策略 {failures}; 行情缺失 {missing}; 模型刷新 {model_issue or "正常"}')
    state={'completed_key':key,'last_completed':datetime.now(timezone.utc).isoformat(),
           'signals':str(signals),'feed':str(feed)}
    atomic_json(state_path,state)
    status(root,'waiting',**state)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.home()/'.quantit/history/2026-07-01')
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    root=args.root
    root.mkdir(parents=True,exist_ok=True)
    config=json.loads((root/'service-config.json').read_text())
    logging.basicConfig(level=logging.INFO,handlers=[RotatingFileHandler(root/'service.log',maxBytes=1_000_000,backupCount=3)],
                        format='%(asctime)s %(levelname)s %(message)s')
    for sig in (signal.SIGTERM,signal.SIGINT):
        signal.signal(sig,lambda *_:STOP.set())
    with (root/'.service.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        while not STOP.is_set():
            failed=False
            try:
                cycle(root,config)
            except Exception as exc:
                failed=True
                logging.exception('History continuation failed')
                status(root,'error',error=str(exc))
            if args.once:
                raise SystemExit(int(failed))
            # Heartbeat every ten minutes; failed expensive jobs retry hourly.
            for _ in range(6 if failed else 1):
                if STOP.wait(600):
                    break
                if failed:
                    current=json.loads((root/'service.json').read_text())
                    status(root,'error',error=current.get('error','待重试'))
        status(root,'stopped')


if __name__=='__main__':
    main()
