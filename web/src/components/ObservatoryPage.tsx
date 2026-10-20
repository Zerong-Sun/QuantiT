import { useEffect, useRef, useState } from "react";
import { createChart } from "lightweight-charts";

type Point = { date: string; value: number | null };
type Indicator = { id: string; name: string; region: string; frequency: string; unit: string; kind: string;
  note: string; provider: string; source_url: string; latest: Point | null; previous: Point | null;
  change: number | null; first_date: string | null; last_date: string | null; count: number; missing_periods: number;
  fetched_at: string | null; error: string | null; cache_stale: boolean; state: string;
  source_notice?: string; download_url?: string; observation_stale: boolean };
type Catalog = { series: Indicator[]; service: { state: string; fresh: boolean }; revision_note: string };
type Curve = { series: Indicator; observations: Point[]; view: string; view_label: string; unit: string; years: number;
  requested_start: string | null; coverage_short: boolean; view_first_date: string | null };
type Article = { id: string; title: string; url: string; source: string; region: string; published_at: string | null; tags: string[] };
type News = { articles: Article[]; matched_count: number; updated_at: string | null; note: string;
  truncated: boolean;
  sources: { id: string; name: string; fetched_at?: string; error?: string; stale: boolean }[] };
type Tab = "macro" | "factors" | "news";
type View = "level" | "change" | "volatility";

const format = (x: number | null | undefined, digits = 2) => x == null ? "—" : x.toLocaleString("zh-CN", { maximumFractionDigits: digits });
const stamp = (date: string | null | undefined) => date ? new Date(date).toLocaleString("zh-CN", { hour12: false }) : "尚未获取";
const period = (date: string | null | undefined, frequency: string) => !date ? "—" : frequency === "M" ? date.slice(0, 7) :
  frequency === "Y" ? date.slice(0, 4) : frequency === "Q" ? `${date.slice(0, 4)} Q${Math.ceil(Number(date.slice(5, 7)) / 3)}` : date;
const frequencyName = (x: string) => ({ M: "月度", Q: "季度", Y: "年度", D: "交易日" }[x] ?? x);
const sourceSafe = (url: string) => /^https?:\/\//.test(url) || url === "/research";

function useData<T>(url: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setData(null); setError("");
    let loading = false;
    async function load() {
      if (loading) return;
      loading = true;
      try {
        const response = await fetch(url, { signal: controller.signal });
        if (!response.ok) throw new Error(`读取失败（${response.status}）`);
        const result = await response.json();
        if (!controller.signal.aborted) { setData(result); setError(""); }
      } catch (e) {
        if (!controller.signal.aborted) setError(e instanceof Error ? e.message : String(e));
      } finally { loading = false; }
    }
    void load();
    const timer = window.setInterval(load, 60_000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [url]);
  return { data, error };
}

function IndicatorChart({ curve }: { curve: Curve }) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!host.current) return;
    const chart = createChart(host.current, { width: host.current.clientWidth, height: 330,
      layout: { background: { color: "#ffffff" }, textColor: "#66766f" },
      grid: { vertLines: { color: "#f0f3f1" }, horzLines: { color: "#edf1ee" } },
      rightPriceScale: { borderVisible: false }, timeScale: { borderVisible: false },
      localization: { locale: "zh-CN" } });
    const series = chart.addLineSeries({ color: curve.view === "volatility" ? "#a77836" : "#28725a", lineWidth: 2,
      priceFormat: { type: "custom", formatter: (value: number) => `${format(value, curve.unit === "IC" ? 3 : 2)}${curve.unit === "%" ? "%" : ""}` } });
    series.setData(curve.observations.map(p => p.value == null ? { time: p.date } : { time: p.date, value: p.value }));
    if (curve.view !== "volatility" && (curve.series.kind !== "macro" || curve.view === "change"))
      series.createPriceLine({ price: 0, color: "#a1b1a7", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "零线" });
    if (curve.view === "level" && ["cn_pmi", "cn_nonmanufacturing"].includes(curve.series.id))
      series.createPriceLine({ price: 50, color: "#b49a68", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "荣枯线" });
    chart.timeScale().fitContent();
    const observer = new ResizeObserver(() => chart.applyOptions({ width: host.current?.clientWidth ?? 320 }));
    observer.observe(host.current);
    return () => { observer.disconnect(); chart.remove(); };
  }, [curve]);
  return <div className="observatory-chart" ref={host} aria-label={`${curve.series.name}，${curve.view_label}历史曲线；具体数值见逐期数据表`} />;
}

function SeriesPanel({ selected, years, view, setYears, setView }: {
  selected: string; years: number; view: View; setYears: (x: number) => void; setView: (x: View) => void;
}) {
  const url = `/api/v1/observatory/series/${encodeURIComponent(selected)}?years=${years}&view=${view}`;
  const { data: curve, error } = useData<Curve>(url);
  const [page, setPage] = useState(0);
  useEffect(() => setPage(0), [selected, years, view]);
  const info = curve?.series;
  const rows = curve?.observations.slice().reverse() ?? [];
  const finite = curve?.observations.filter(p => p.value != null) ?? [];
  return <section className="observatory-panel observatory-detail">
    {error ? <p role="alert" className="history-notice">{error}，已有数据仍保留。</p> : null}
    <div className="observatory-chart-heading"><div><p className="eyebrow">{info?.kind === "macro" ? "ECONOMIC INDICATOR" : "FACTOR MONITOR"}</p>
      <h2>{info?.name ?? "读取指标…"}</h2><p className="hint">{info ? `${frequencyName(info.frequency)} · ${info.provider}` : "正在读取缓存"}</p></div>
      <div className="observatory-range" role="group" aria-label="历史范围">
        {[[5, "5 年"], [10, "10 年"], [50, "50 年"], [0, "全部"]] .map(([n, label]) =>
          <button key={n} aria-pressed={years === n} onClick={() => setYears(Number(n))}>{label}</button>)}
      </div>
    </div>
    {info ? <>
      <div className="observatory-metrics">
        <div><span>最新原始指标 · {info.unit}</span><strong>{format(info.latest?.value, info.unit === "IC" ? 4 : 2)}</strong><small>所属期 {period(info.latest?.date, info.frequency)}</small></div>
        <div><span>较上期变化 · {info.unit === "%" ? "百分点" : info.unit}</span><strong>{info.change != null && info.change > 0 ? "+" : ""}{format(info.change, info.unit === "IC" ? 4 : 2)}</strong><small>上期 {period(info.previous?.date, info.frequency)} · {format(info.previous?.value)}</small></div>
        <div><span>真实历史覆盖</span><strong className="observatory-date">{period(info.first_date, info.frequency)}</strong><small>至 {period(info.last_date, info.frequency)} · {info.count.toLocaleString()} 个有效观测</small></div>
      </div>
      <div className="observatory-viewbar"><label>曲线口径 <select aria-label="曲线口径" value={view} onChange={e => setView(e.target.value as View)}>
        <option value="level">{info.kind === "factor" ? "每月因子收益" : info.kind === "local_factor" ? "每日 Rank IC" : "指标值"}</option>
        {info.kind === "macro" ? <option value="change">较上期变化</option> : <option value="volatility">{info.kind === "factor" ? "12 个月滚动年化波动" : "21 日 IC 波动"}</option>}
      </select></label><span>{curve?.view_label} · 单位 {curve?.unit}</span></div>
      {info.error || info.cache_stale ? <details className="history-notice"><summary>{info.count ? "当前显示已缓存数据，最近刷新待恢复" : "此数据源暂未取得可用数据"}</summary><p>{info.error ?? "等待后台刷新"}</p></details> : null}
      {info.source_notice ? <p className="observatory-coverage">{info.source_notice} {info.download_url && sourceSafe(info.download_url) ? <a href={info.download_url} target="_blank" rel="noreferrer">快照来源 ↗</a> : null}</p> : info.observation_stale && info.count ? <p className="observatory-coverage">最新观测距今较久，请核对数据源是否暂停发布；成功抓取不代表观测已更新。</p> : null}
      {curve?.coverage_short ? <p className="observatory-coverage">不足 {years} 年，仅展示实际覆盖：{period(info.first_date, info.frequency)} 起。不补造或拼接其他指标。</p> : null}
      {finite.length > 0 && curve ? <IndicatorChart curve={curve} /> : <div className="observatory-empty" role="status">这个范围或口径尚无有效数据。可切换“全部”查看覆盖范围。</div>}
      <p className="observatory-definition">{info.note}</p>
      <div className="observatory-provenance"><span>最近成功抓取 {stamp(info.fetched_at)}</span>{sourceSafe(info.source_url) ? <a href={info.source_url} target="_blank" rel="noreferrer">查看原始来源 ↗</a> : null}</div>
      <details className="observatory-periods">
        <summary>逐期数据与下载 <span>{rows.length} 期 · 当前曲线口径</span></summary>
        <div className="observatory-download"><span>缺失观测显示为“—”，不会填为 0。</span><a href={`${url}&output=csv`} download>下载 CSV ↓</a></div>
        <div className="history-scroll"><table><thead><tr><th>数据所属期</th><th>{curve?.view_label} · {curve?.unit}</th></tr></thead>
          <tbody>{rows.slice(page * 12, page * 12 + 12).map(p => <tr key={p.date}><td>{period(p.date, info.frequency)}</td><td>{format(p.value, curve?.unit === "IC" ? 4 : 3)}</td></tr>)}</tbody></table></div>
        <div className="history-pagination"><button disabled={!page} onClick={() => setPage(p => p - 1)}>较新一期</button><span>{page + 1} / {Math.max(1, Math.ceil(rows.length / 12))}</span><button disabled={(page + 1) * 12 >= rows.length} onClick={() => setPage(p => p + 1)}>更早一期</button></div>
      </details>
    </> : <div role="status" className="observatory-empty">正在读取历史序列…</div>}
  </section>;
}

function NewsPanel() {
  const [region, setRegion] = useState("ALL");
  const [tag, setTag] = useState("");
  const [query, setQuery] = useState("");
  const [days, setDays] = useState(7);
  const [page, setPage] = useState(0);
  const params = new URLSearchParams({ region, tag, q: query, days: String(days) });
  const { data, error } = useData<News>(`/api/v1/observatory/news?${params}`);
  useEffect(() => setPage(0), [region, tag, query, days]);
  return <section className="observatory-panel">
    <div className="observatory-chart-heading"><div><h2>新闻与事件观察</h2><p className="hint">每 15 分钟检查公开订阅源 · 按来源发布时间排序</p></div>
      <span className="status-pill neutral">{data?.matched_count ?? 0} 条匹配</span></div>
    <div className="observatory-news-filters">
      <label>地区<select aria-label="新闻地区" value={region} onChange={e => setRegion(e.target.value)}><option value="ALL">全部地区</option><option value="CN">中国</option><option value="US">美国</option><option value="GLOBAL">全球</option></select></label>
      <label>类型<select aria-label="新闻类型" value={tag} onChange={e => setTag(e.target.value)}><option value="">全部类型</option>{["突发风险线索", "政策与利率", "经济数据", "市场动态"].map(x => <option key={x}>{x}</option>)}</select></label>
      <label>范围<select aria-label="新闻日期范围" value={days} onChange={e => setDays(Number(e.target.value))}><option value={7}>最近 7 天</option><option value={30}>最近 30 天</option><option value={0}>全部已存档</option></select></label>
      <label className="observatory-search">关键词<input aria-label="新闻关键词" placeholder="例如：关税、利率、inflation" value={query} onChange={e => setQuery(e.target.value)} /></label>
    </div>
    {error ? <p role="alert">{error}</p> : null}
    <div className="observatory-source-status">{data?.sources.map(s => <span className={s.error || s.stale ? "source-warning" : ""} key={s.id} title={s.error ?? stamp(s.fetched_at)}>{s.name} · {s.error ? "更新失败，保留缓存" : s.stale ? "等待更新" : "已更新"}</span>)}</div>
    {data?.truncated ? <p className="observatory-coverage">匹配超过 300 条，目前展示最新 300 条。可通过地区、类型或关键词缩小范围。</p> : null}
    {!data ? <p role="status">正在读取新闻…</p> : !data.articles.length ? <div className="observatory-empty">当前筛选没有新闻。没有结果不代表没有风险；可扩大日期或清除关键词。</div> :
      <div className="observatory-news-list">{data.articles.slice(page * 12, page * 12 + 12).map(a => <article key={a.id}>
        <div className="observatory-news-meta"><span>{a.source}</span><time>{stamp(a.published_at)}</time></div>
        <a href={sourceSafe(a.url) ? a.url : undefined} target="_blank" rel="noreferrer">{a.title} <span aria-hidden="true">↗</span></a>
        <div className="observatory-tags">{a.tags.map(t => <span className={t === "突发风险线索" ? "risk" : ""} key={t}>{t}</span>)}</div>
      </article>)}</div>}
    <div className="history-pagination"><button disabled={!page} onClick={() => setPage(p => p - 1)}>上一页</button><span>{page + 1} / {Math.max(1, Math.ceil((data?.articles.length ?? 0) / 12))}</span><button disabled={(page + 1) * 12 >= (data?.articles.length ?? 0)} onClick={() => setPage(p => p + 1)}>下一页</button></div>
    <p className="observatory-definition">{data?.note} 仅展示标题和原文链接；新闻不触发交易。可查询存档从接入时开始，保留最近 5,000 条，不能查询未收录的历史事件。</p>
  </section>;
}

export function ObservatoryPage() {
  const { data: catalog, error } = useData<Catalog>("/api/v1/observatory");
  const [tab, setTab] = useState<Tab>("macro");
  const [region, setRegion] = useState("US");
  const [selected, setSelected] = useState("us_payroll");
  const [years, setYears] = useState(5);
  const [view, setView] = useState<View>("level");
  const matching = catalog?.series.filter(s => (tab === "macro" ? s.kind === "macro" : s.kind !== "macro") && s.region === region) ?? [];
  function changeTab(next: Tab) {
    setTab(next); setView("level");
    setSelected(next === "macro" ? (region === "US" ? "us_payroll" : "cn_cpi") : (region === "US" ? "ff_market" : "local_alpha158_lgbm_h1"));
  }
  function changeRegion(next: string) {
    setRegion(next); setView("level");
    setSelected(tab === "macro" ? (next === "US" ? "us_payroll" : "cn_cpi") : (next === "US" ? "ff_market" : "local_alpha158_lgbm_h1"));
  }
  const online = catalog?.service.fresh && ["waiting", "refreshing"].includes(catalog.service.state);
  return <main className="overview-page observatory-page">
    <div className="page-heading"><div><p className="eyebrow">MACRO & EVENTS</p><h1>把策略放回市场环境中观察</h1><p>经济数据看周期，新闻看变化，因子看稳定性。</p></div>
      <span className={`status-pill ${online ? "success" : "warning"}`}>{online ? catalog?.service.state === "refreshing" ? "数据更新中" : "观察服务在线" : "观察服务待确认"}</span></div>
    <div className="observatory-tabs" role="tablist" aria-label="宏观栏目">
      {([["macro", "经济数据", "非农 · 通胀 · 增长"], ["news", "新闻事件", "政策 · 市场 · 风险"], ["factors", "因子走势", "收益 · IC · 波动"]] as const).map(([id, label, description]) =>
        <button role="tab" aria-selected={tab === id} key={id} onClick={() => changeTab(id)}><strong>{label}</strong><span>{description}</span></button>)}
    </div>
    {error ? <p role="alert" className="history-notice">{error}</p> : null}
    {tab === "news" ? <NewsPanel /> : <>
      <div className="observatory-regionbar"><div role="group" aria-label="数据地区">{[["US", "美国"], ["CN", "中国"]].map(([id, label]) =>
        <button aria-pressed={region === id} key={id} onClick={() => changeRegion(id)}>{label}</button>)}</div>
        <p>{tab === "macro" ? "按原始月度、季度或年度频率逐期查看" : region === "US" ? "Fama–French 五因子 · 可查 50 年月度历史" : "本项目样本外预测效果 · 历史长度以真实研究记录为准"}</p></div>
      <div className="observatory-layout"><aside className="observatory-panel observatory-picker" aria-label="指标列表">
        <h2>{tab === "macro" ? "关键经济指标" : "选择因子"}</h2>
        {matching.map(s => <button key={s.id} aria-pressed={selected === s.id} onClick={() => { setSelected(s.id); setView("level"); }}>
          <span className="observatory-indicator-name">{s.name}</span><span className="observatory-indicator-value">{format(s.latest?.value, s.unit === "IC" ? 3 : 2)} <small>{s.unit}</small></span>
          <small>{period(s.latest?.date, s.frequency)} · {frequencyName(s.frequency)}{s.state !== "ready" ? " · " + (s.count ? "缓存" : "待获取") : ""}</small>
        </button>)}
        {!catalog ? <p role="status">正在加载指标…</p> : null}
      </aside><SeriesPanel selected={selected} years={years} view={view} setYears={setYears} setView={setView} /></div>
      <details className="observatory-method"><summary>数据口径、更新频率与历史边界</summary>
        <p>{catalog?.revision_note} 未接入市场一致预期、首次公布值及完整经济日历，因此不显示“超预期”评分。</p>
        <p>经济与因子数据每 6 小时检查一次；新闻每 15 分钟检查。数据源失败时保留上次成功缓存并显示状态。图表范围按今天向前计算，50 年按钮不会补造缺失历史。日历缺期保留空值，图表不把空值当作零。</p>
        <p>经济指标、美国学术因子、本项目预测 IC 分别展示。研究因子收益不代表可直接交易的净收益，IC 也不是收益率。本栏目用于观察，不改变策略参数或发出交易订单。</p>
      </details>
    </>}
  </main>;
}
