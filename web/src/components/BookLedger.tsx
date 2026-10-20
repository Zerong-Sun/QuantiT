import { useState } from "react";
import type { Order, Position, Trade } from "../types";
import { instrumentLabel } from "../markets/display";
import { marketUi } from "../markets/config";

type Tab = "positions" | "trades" | "orders";
const SIZE = 20;
const number = (n: number) => n.toLocaleString("zh-CN", { maximumFractionDigits: 3 });
const side = (s: string) => s === "buy" ? "买入" : s === "sell" ? "卖出" : s;
const status = (s: string) => ({ filled: "已成交", rejected: "已拒绝", pending: "待处理" }[s] ?? s);

export function BookLedger({ market, positions, trades, orders, onSymbol, onOrder }: {
  market: string; positions: Position[]; trades: Trade[]; orders: Order[];
  onSymbol: (symbol: string) => void; onOrder: (order: Order) => void;
}) {
  const [tab, setTab] = useState<Tab>("positions");
  const [page, setPage] = useState(0);
  const pos = positions.filter((p) => p.market_id === market);
  const tr = trades.filter((t) => t.market_id === market).sort((a, b) => b.id - a.id);
  const ord = orders.filter((o) => o.market_id === market).sort((a, b) => b.id - a.id);
  const total = tab === "positions" ? pos.length : tab === "trades" ? tr.length : ord.length;
  const pages = Math.max(1, Math.ceil(total / SIZE));
  const current = Math.min(page, pages - 1);
  const start = current * SIZE;
  const label = (item: Position | Trade | Order) => instrumentLabel(market, item.symbol, item.name);
  return <section className="book-ledger" aria-label="当前策略账户记录">
    <div className="ledger-toolbar">
      <div className="desk-tabs">
        {([["positions", "当前持仓", pos.length], ["trades", "成交记录", tr.length], ["orders", "委托记录", ord.length]] as const).map(([id, title, count]) =>
          <button key={id} aria-pressed={tab === id} className={tab === id ? "active" : ""} onClick={() => { setTab(id); setPage(0); }}>{title} <small>{count}</small></button>)}
      </div><span>{marketUi(market).label} · {tab === "trades" ? "时间为 UTC" : "仅当前账户"}</span>
    </div>
    <div className="ledger-table"><table>
      <thead><tr>{(tab === "positions" ? ["标的", "数量", "持仓均价"] : tab === "trades" ? ["成交时间 (UTC)", "标的", "方向", "数量", "成交价"] : ["委托编号", "标的", "状态", "数量", "依据 / 拒绝原因"]).map((h) => <th key={h}>{h}</th>)}</tr></thead>
      <tbody>
        {total === 0 ? <tr><td colSpan={5} className="empty">当前账户暂无{tab === "positions" ? "持仓" : tab === "trades" ? "成交" : "委托"}记录</td></tr> : null}
        {tab === "positions" ? pos.slice(start, start + SIZE).map((p) => <tr key={p.symbol}>
          <td><button className="text-button" onClick={() => onSymbol(p.symbol)}>{label(p)}</button></td><td>{number(p.quantity)}</td><td>{number(p.avg_cost)}</td>
        </tr>) : null}
        {tab === "trades" ? tr.slice(start, start + SIZE).map((t) => <tr key={t.id}>
          <td>{t.timestamp.replace("T", " ").slice(0, 19)}</td><td>{label(t)}</td><td className={t.side}>{side(t.side)}</td><td>{number(t.quantity)}</td><td>{number(t.price)}</td>
        </tr>) : null}
        {tab === "orders" ? ord.slice(start, start + SIZE).map((o) => <tr key={o.id}>
          <td><button className="text-button" onClick={() => onOrder(o)}>#{o.id}</button></td><td>{label(o)}</td><td>{status(o.status)}</td><td>{number(o.quantity)}</td>
          <td><details><summary>{o.reject_reason ? "查看拒绝原因" : o.rationale?.includes("[historical reconstruction]") ? "历史重建" : "查看执行依据"}</summary><p className="order-reason">{o.reject_reason || o.rationale || "无附加说明"}</p></details></td>
        </tr>) : null}
      </tbody>
    </table></div>
    <footer className="pagination"><span>共 {total} 条 · 第 {current + 1} / {pages} 页</span>
      <button disabled={current === 0} onClick={() => setPage(current - 1)}>上一页</button>
      <button disabled={current >= pages - 1} onClick={() => setPage(current + 1)}>下一页</button>
    </footer>
  </section>;
}
