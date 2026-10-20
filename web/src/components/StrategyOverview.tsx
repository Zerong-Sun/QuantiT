import type { Account, Market, Runner } from "../types";
import { marketUi } from "../markets/config";

export function bookState(runner: Runner | null, id: string) {
  const recovery = runner?.recovery?.[id];
  const current = runner?.books?.[id];
  if (recovery && recovery.status !== "complete")
    return { label: "恢复阻塞", tone: "warning", detail: recovery.detail };
  if (current?.state === "error" || current?.state === "blocked")
    return { label: "需要检查", tone: "warning", detail: current.error };
  if (!runner) return { label: "等待连接", tone: "neutral", detail: null };
  if (!runner.auto_books?.includes(id)) return { label: "手动评估", tone: "neutral", detail: null };
  if (!runner.running) return { label: "已暂停", tone: "neutral", detail: null };
  if (current?.state === "evaluating") return { label: "评估中", tone: "neutral", detail: null };
  if (current?.state === "evaluated") return { label: "自动运行", tone: "success", detail: null };
  return { label: "等待评估", tone: "neutral", detail: null };
}

const descriptions: Record<string, string> = {
  us: "质量股票池 · 趋势与波动率控制",
  us_book: "均线 / RSI · 期权附加模块",
  hk: "港股质量组合 · 趋势配置",
  hk_theme: "恒生科技主题 · 行业轮动",
  cn: "A 股质量组合 · 趋势配置",
  cn_etf: "行业 ETF · 主题轮动",
};

export function StrategyOverview({ markets, accounts, runner, onOpen, onResearch }: {
  markets: Market[]; accounts: Account[]; runner: Runner | null;
  onOpen: (id: string) => void; onResearch: () => void;
}) {
  const books = markets.filter((m) => m.id !== "cl");
  const blocked = books.filter((b) => bookState(runner, b.id).tone === "warning").length;
  const complete = books.filter((b) => runner?.recovery?.[b.id]?.status === "complete").length;
  return <main className="overview-page">
    <div className="page-heading">
      <div><p className="eyebrow">STRATEGY MONITOR</p><h1>策略总览</h1>
        <p>先看运行状态，再进入账户查看行情、持仓和执行记录。</p></div>
      <span className="environment-label">模拟交易 · 资金按账户隔离</span>
    </div>
    <div className="overview-metrics">
      <div><span>独立策略</span><strong>{books.length || "—"}</strong><small>另有独立因子研究账户</small></div>
      <div><span>历史恢复完成</span><strong>{runner ? complete : "—"}</strong><small>按各市场完整交易日补跑</small></div>
      <div><span>需要关注</span><strong className={blocked ? "warning-text" : ""}>{runner ? blocked : "—"}</strong><small>阻塞账户不影响其他策略</small></div>
    </div>
    <div className="section-heading"><h2>策略账户</h2><span>现金按原币种展示，不跨币种相加</span></div>
    {!books.length ? <p className="empty">正在连接策略账户…</p> : null}
    <div className="strategy-grid">
      {books.map((book, i) => {
        const state = bookState(runner, book.id);
        const account = accounts.find((a) => a.market_id === book.id);
        const recovery = runner?.recovery?.[book.id];
        return <article className="strategy-card" key={book.id}>
          <div className="strategy-card-top"><span className="book-number">0{i + 1}</span>
            <span className={`status-pill ${state.tone}`}>{state.label}</span></div>
          <h3>{marketUi(book.id).label}</h3><p>{descriptions[book.id]}</p>
          <div className="book-cash"><span>可用现金 · {book.currency}</span>
            <strong>{account?.cash.toLocaleString("zh-CN", { maximumFractionDigits: 2, minimumFractionDigits: 2 }) ?? "—"}</strong></div>
          <div className="recovery-line">{recovery
            ? `${recovery.status === "complete" ? "历史补跑至" : "历史恢复阻塞于"} ${recovery.day}`
            : "尚无历史恢复记录"}</div>
          {state.detail ? <details className="status-detail"><summary>查看阻塞原因</summary><p>{state.detail}</p></details> : null}
          <button className="open-book" onClick={() => onOpen(book.id)} aria-label={`打开${marketUi(book.id).label}`}>进入工作台 <span aria-hidden="true">↗</span></button>
        </article>;
      })}
    </div>
    <aside className="research-link"><div><h2>因子研究</h2><p>独立查看 Alpha101 因子、验证门槛与研究账户。</p></div>
      <button onClick={onResearch}>打开研究空间 →</button></aside>
  </main>;
}
