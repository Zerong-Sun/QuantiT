import { useEffect, useRef, useState } from "react";
import { createChart } from "lightweight-charts";

type Day = { day: string; signal_through: string; equity: number; cash: number; receivable: number;
  total_return: number; drawdown: number; daily_pnl: number; fees: number; fills: number; rejected: number;
  stale_symbols: string[]; status: string };
type Detail = Day & { positions: { symbol: string; quantity: number; close: number; value: number; price_date: string }[];
  orders: { symbol: string; side: string; quantity: number; price: number; fee: number; status: string; reason: string }[];
  corporate_actions: { symbol: string; type: string; amount?: number; ratio?: number }[] };
type Strategy = { id: string; name: string; currency: string; initial_cash: number; equity: number | null;
  total_return: number | null; max_drawdown: number; fees: number; fills: number; sessions: number;
  last_day: string | null; status: string; error: { day: string; error: string } | string | null;
  model: { train_end?: string } | null; days: Day[] };
type Report = { ready: boolean; start: string; requested_end: string; updated_at: string; limitations: string[];
  strategies: Strategy[]; service: { state: string; fresh: boolean; heartbeat?: string; error?: string } };
const number = (x: number | null | undefined, digits = 2) => x == null ? "—" : x.toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
const pct = (x: number | null | undefined) => x == null ? "—" : `${number(x * 100)}%`;
async function get<T,>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, { signal });
  if (!res.ok) throw new Error(`历史数据读取失败 (${res.status})`);
  return res.json();
}

function EquityChart({ strategy }: { strategy: Strategy }) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!host.current) return;
    const chart = createChart(host.current, { width: host.current.clientWidth, height: 270,
      layout: { background: { color: "#ffffff" }, textColor: "#66766f" },
      grid: { vertLines: { color: "#edf1ee" }, horzLines: { color: "#edf1ee" } },
      localization: { locale: "zh-CN" }, rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false } });
    const series = chart.addAreaSeries({ lineColor: "#28725a", topColor: "#cde5d8", bottomColor: "#ffffff",
      priceFormat: { type: "percent", precision: 2, minMove: .01 } });
    series.setData(strategy.days.map(d => ({ time: d.day, value: d.total_return * 100 })));
    series.createPriceLine({ price: 0, color: "#94a39b", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "起始资金" });
    chart.timeScale().fitContent();
    const observer = new ResizeObserver(() => chart.applyOptions({ width: host.current?.clientWidth ?? 300 }));
    observer.observe(host.current);
    return () => { observer.disconnect(); chart.remove(); };
  }, [strategy]);
  return <div ref={host} className="history-chart" aria-label={`${strategy.name}自起始资金以来的扣费收益曲线，数值可查下方逐日表`} />;
}

export function HistoryPage() {
  const [report, setReport] = useState<Report | null>(null);
  const [selected, setSelected] = useState("alpha158_lgbm_h10");
  const [day, setDay] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [page, setPage] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const refresh = () => get<Report>("/api/v1/history", controller.signal).then(r => {
      setReport(r); setError("");
      setSelected(prev => r.strategies.some(s => s.id === prev) ? prev : r.strategies[0]?.id ?? "");
    }).catch(e => { if (!controller.signal.aborted) setError(String(e)); });
    void refresh();
    const timer = window.setInterval(refresh, 60_000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, []);
  const strategy = report?.strategies.find(s => s.id === selected);
  useEffect(() => { setDay(strategy?.last_day ?? ""); setPage(0); }, [selected]);
  const shownDay = day && strategy?.days.some(d => d.day === day) ? day : strategy?.last_day ?? "";
  useEffect(() => {
    setDetail(null); setDetailError("");
    if (!selected || !shownDay) return;
    const controller = new AbortController();
    get<Detail>(`/api/v1/history/${encodeURIComponent(selected)}/${shownDay}`, controller.signal)
      .then(setDetail).catch(e => { if (!controller.signal.aborted) setDetailError(String(e)); });
    return () => controller.abort();
  }, [selected, shownDay]);
  const dates = strategy?.days.slice().reverse() ?? [];
  const service = report?.service;
  const running = service?.fresh && ["waiting", "running"].includes(service.state);
  return <main className="overview-page history-page">
    <div className="page-heading"><div><p className="eyebrow">DAILY PAPER HISTORY</p>
      <h1>从 7 月 1 日开始，逐日检验策略</h1>
      <p>11 个独立模拟账户 · 前日信号、次日开盘成交 · 保留原账户记录</p></div>
      <span className={`status-pill ${running ? "success" : "warning"}`}>{running ? "历史续跑服务在线" : service?.fresh ? "历史续跑待恢复" : "历史续跑状态待确认"}</span>
    </div>
    {error ? <p role="alert" className="history-notice">{error}</p> : null}
    {service?.error ? <details className="history-notice"><summary>续跑服务最近异常</summary><p>{service.error}</p></details> : null}
    {!report ? <p role="status">正在读取历史记录…</p> : !report.ready ? <p>历史实验尚未完成，完成后会在这里显示。</p> : <>
      <div className="history-notice">起点 {report.start}，已请求至 {report.requested_end}。仅结算已收盘的交易日，各市场最新日期可能不同。收益已经扣除模拟手续费和滑点，不能视为实盘成交结果。</div>
      <div className="history-layout">
        <section className="history-panel history-picker"><div className="section-heading"><h2>选择策略</h2><span>累计收益 / 最大回撤</span></div>
          {report.strategies.map(s => <button key={s.id} aria-pressed={selected === s.id} onClick={() => setSelected(s.id)}>
            <span><strong>{s.name}</strong><small>{s.currency} · {s.last_day ?? "等待行情"}{s.status === "blocked" ? " · 待恢复" : ""}</small></span>
            <span><b className={(s.total_return ?? 0) >= 0 ? "up" : "down"}>{pct(s.total_return)}</b><small>{pct(s.max_drawdown)}</small></span>
          </button>)}
        </section>
        {strategy ? <section className="history-panel history-result"><div className="section-heading"><h2>{strategy.name}</h2><span>{strategy.sessions} 个交易日 · 截至 {strategy.last_day ?? "—"}</span></div>
          {strategy.error ? <p role="alert" className="history-notice">未跳过异常日：{typeof strategy.error === "string" ? strategy.error : `${strategy.error.day} · ${strategy.error.error}`}</p> : null}
          <div className="history-metrics"><div><span>期末权益 · {strategy.currency}</span><strong>{number(strategy.equity)}</strong><small>初始 {number(strategy.initial_cash, 0)}</small></div>
            <div><span>累计扣费收益</span><strong className={(strategy.total_return ?? 0) >= 0 ? "up" : "down"}>{pct(strategy.total_return)}</strong><small>最大回撤 {pct(strategy.max_drawdown)}</small></div>
            <div><span>成交 / 手续费</span><strong>{strategy.fills} 笔</strong><small>{number(strategy.fees)} {strategy.currency}</small></div></div>
          <EquityChart strategy={strategy} />
          <p className="hint">{strategy.model?.train_end ? `模型训练截止 ${strategy.model.train_end}，参数已冻结。` : "规则与参数在本实验开始时冻结。"}曲线为每日收盘相对初始资金的收益率；股息应收计入权益。</p>
          <div className="section-heading"><h2>逐日记录</h2><span>选择日期查看持仓和订单</span></div>
          <div className="history-scroll"><table><thead><tr><th>日期</th><th>权益</th><th>当日盈亏</th><th>成交</th><th>未成交</th></tr></thead><tbody>
            {dates.slice(page * 8, page * 8 + 8).map(d => <tr key={d.day} className={d.day === shownDay ? "selected" : ""}><td><button aria-pressed={d.day === shownDay} onClick={() => setDay(d.day)}>{d.day}</button></td>
              <td>{number(d.equity)}</td><td className={d.daily_pnl >= 0 ? "up" : "down"}>{number(d.daily_pnl)}</td><td>{d.fills}</td><td>{d.rejected}{d.stale_symbols.length ? " · 估值待核验" : ""}</td></tr>)}
          </tbody></table></div>
          <div className="history-pagination"><button disabled={page === 0} onClick={() => setPage(p => p - 1)}>较新日期</button><span>{page + 1} / {Math.max(1, Math.ceil(dates.length / 8))}</span><button disabled={(page + 1) * 8 >= dates.length} onClick={() => setPage(p => p + 1)}>更早日期</button></div>
        </section> : null}
      </div>
      <section className="history-panel history-detail" aria-busy={!detail && !detailError && !!shownDay}>
        <div className="section-heading"><h2>{strategy?.name} · {shownDay || "尚无结算"}</h2><label>交易日期 <select value={shownDay} onChange={e => setDay(e.target.value)} aria-label="历史交易日期">{dates.map(d => <option key={d.day}>{d.day}</option>)}</select></label></div>
        {detailError ? <p role="alert">{detailError}</p> : !detail ? <p>{shownDay ? "正在读取当日持仓与订单…" : "尚无逐日明细"}</p> : <>
          <div className="experiment-context"><span>信号截至 {detail.signal_through}</span><span>可用现金 {number(detail.cash)}</span><span>股息等应收 {number(detail.receivable)}</span><span>当日费用 {number(detail.fees)}</span></div>
          {detail.stale_symbols.length ? <p className="history-notice">停牌、零成交量或缺少当日行情，使用最近可用参考价估值，不能视为可成交价格：{detail.stale_symbols.join("、")}</p> : null}
          <div className="history-detail-grid"><div><h3>收盘持仓</h3><div className="history-scroll"><table><thead><tr><th>标的</th><th>数量</th><th>收盘价</th><th>市值</th></tr></thead><tbody>{detail.positions.map(p => <tr key={p.symbol}><td>{p.symbol}{detail.stale_symbols.includes(p.symbol) ? <small>参考估值 · {p.price_date}</small> : null}</td><td>{number(p.quantity,0)}</td><td>{number(p.close,3)}</td><td>{number(p.value)}</td></tr>)}</tbody></table></div>{!detail.positions.length ? <p className="hint">当日空仓</p> : null}</div>
          <div><h3>当日订单</h3><div className="history-scroll"><table><thead><tr><th>标的 / 方向</th><th>数量</th><th>成交价 / 费用</th><th>结果</th></tr></thead><tbody>{detail.orders.map((o,i) => <tr key={i}><td>{o.symbol}<small>{o.side === "buy" ? "买入" : "卖出"}</small></td><td>{number(o.quantity,0)}</td><td>{o.status === "filled" ? number(o.price,3) : "—"}<small>{number(o.fee)}</small></td><td><details><summary>{o.status === "filled" ? "已成交" : "未成交"}</summary><p>{o.reason}</p></details></td></tr>)}</tbody></table></div>{!detail.orders.length ? <p className="hint">当日无订单，按原持仓继续持有。</p> : null}</div></div>
          {detail.corporate_actions.length ? <details><summary>当日公司行动（{detail.corporate_actions.length}）</summary>{detail.corporate_actions.map((a,i) => <p key={i}>{a.symbol} · {a.type === "split" ? `股份调整 ×${a.ratio}` : `股息应收 ${number(a.amount)}`}</p>)}</details> : null}
        </>}
      </section>
      <details className="history-panel history-method"><summary>模拟口径与适用边界</summary><ul>{report.limitations.map(x => <li key={x}>{x}</li>)}</ul><p>本页覆盖六个交易台策略及五个冻结研究策略。动态筛选 Alpha101 因子的 CL 研究账户保留在因子研究页，未将当前入选因子倒填为 7 月的历史决策。</p><p>每个账户独立起步，币种之间不直接相加。美股各 10 万美元，港股各 100 万港币，A 股各 100 万人民币。刷新时间：{new Date(report.updated_at).toLocaleString("zh-CN")}</p></details>
    </>}
  </main>;
}
