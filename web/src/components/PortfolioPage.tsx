import { useEffect, useState } from "react";
import { api } from "../api";
import { BarChart, DonutChart, colorAt } from "./AllocationCharts";
import { ResizableCard } from "./ResizableCard";
import { marketUi } from "../markets/config";
import type { PortfolioBook, PortfolioOverview } from "../types";

function fmt(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) {
    return "—";
  }
  return n.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function pnlClass(n: number | null | undefined): string {
  if (n === null || n === undefined || n === 0) {
    return "";
  }
  return n > 0 ? "up" : "down";
}

export function PortfolioPage() {
  const [data, setData] = useState<PortfolioOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [market, setMarket] = useState("us");

  async function load(opts?: { quiet?: boolean }) {
    if (!opts?.quiet) {
      setLoading(true);
      setError("");
    }
    const ctrl = new AbortController();
    const timer = window.setTimeout(() => ctrl.abort(), 25_000);
    try {
      const next = await api.portfolio(ctrl.signal);
      setData(next);
      setMarket((prev) => (next.books.some((b) => b.market_id === prev) ? prev : next.books[0]?.market_id ?? "us"));
      setError("");
    } catch (err) {
      if (!opts?.quiet) {
        const message = err instanceof Error ? err.message : String(err);
        const aborted = (err instanceof DOMException && err.name === "AbortError") || /abort/i.test(message);
        setError(aborted ? "持仓数据加载超时，请刷新重试。" : message);
      }
    } finally {
      window.clearTimeout(timer);
      if (!opts?.quiet) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    load();
    const timer = window.setInterval(() => load({ quiet: true }).catch(() => undefined), 15_000);
    return () => window.clearInterval(timer);
  }, []);

  const book: PortfolioBook | undefined = data?.books.find((b) => b.market_id === market) ?? data?.books[0];
  const rows = (data?.positions ?? []).filter((p) => p.market_id === (book?.market_id ?? market));
  const slices = rows
    .filter((p) => p.market_value > 0)
    .map((p, i) => ({
      label: p.symbol,
      value: p.market_value,
      color: colorAt(i),
    }));
  const classSlices = Object.values(
    rows.reduce<Record<string, { label: string; value: number; color: string }>>((acc, p, i) => {
      if (p.market_value <= 0) {
        return acc;
      }
      const key = p.asset_class;
      if (!acc[key]) {
        acc[key] = { label: key, value: 0, color: colorAt(i + 4) };
      }
      acc[key].value += p.market_value;
      return acc;
    }, {}),
  );

  return (
    <main className="dashboard">
      <div className="desk-tabs">
        {(data?.books ?? []).map((b) => (
          <button key={b.market_id} className={b.market_id === book?.market_id ? "active" : ""} onClick={() => setMarket(b.market_id)}>
            {marketUi(b.market_id).label} · {b.currency}
          </button>
        ))}
      </div>

      <ResizableCard id="pf-summary" title="Book" className="wide" loading={loading} minWidth={360} minHeight={160}>
        {book ? (
          <div className="metric-grid">
            <div className="metric">
              <span>持仓价值</span>
              <strong>{fmt(book.invested, 0)} {book.currency}</strong>
            </div>
            <div className="metric">
              <span>现金</span>
              <strong>{fmt(book.cash, 0)} {book.currency}</strong>
            </div>
            <div className="metric">
              <span>净值</span>
              <strong>{fmt(book.equity, 0)} {book.currency}</strong>
            </div>
            <div className="metric">
              <span>累计盈亏</span>
              <strong className={pnlClass(book.total_pnl)}>{fmt(book.total_pnl)} {book.currency}</strong>
            </div>
            <div className="metric">
              <span>日盈亏</span>
              <strong className={pnlClass(book.day_pnl)}>{fmt(book.day_pnl)} {book.currency}</strong>
            </div>
            <div className="metric">
              <span>周盈亏</span>
              <strong className={pnlClass(book.week_pnl)}>{fmt(book.week_pnl)} {book.currency}</strong>
            </div>
            <div className="metric">
              <span>月盈亏</span>
              <strong className={pnlClass(book.month_pnl)}>{fmt(book.month_pnl)} {book.currency}</strong>
            </div>
          </div>
        ) : (
          <p className="empty">No account.</p>
        )}
        {error ? <p className="banner error">{error}</p> : null}
        {data?.asof ? <p className="hint asof">as of {data.asof.replace("T", " ").slice(0, 19)} · delayed marks</p> : null}
      </ResizableCard>

      <ResizableCard id="pf-donut" title="持仓分布" className="pane" loading={loading} minWidth={280} minHeight={240}>
        <DonutChart slices={slices} empty="No open positions." />
      </ResizableCard>

      <ResizableCard id="pf-class" title="资产类别" className="pane" loading={loading} minWidth={240} minHeight={240}>
        <DonutChart slices={classSlices} empty="No open positions." />
      </ResizableCard>

      <ResizableCard id="pf-bars" title="持仓市值" className="pane" loading={loading} minWidth={280} minHeight={240}>
        <BarChart slices={slices} empty="No open positions." />
      </ResizableCard>

      <ResizableCard id="pf-table" title="Positions" className="wide" loading={loading} minWidth={360} minHeight={220}>
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Qty</th>
              <th>Last</th>
              <th>Avg</th>
              <th>Value</th>
              <th>Weight</th>
              <th>Unrealized</th>
              <th>Day</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan={8}>No positions</td></tr>
            ) : rows.map((p) => (
              <tr key={`${p.market_id}-${p.symbol}`}>
                <td>{p.symbol}</td>
                <td>{p.quantity}</td>
                <td>{fmt(p.last)}</td>
                <td>{fmt(p.avg_cost)}</td>
                <td>{fmt(p.market_value, 0)}</td>
                <td>{(p.weight * 100).toFixed(1)}%</td>
                <td className={pnlClass(p.unrealized)}>{fmt(p.unrealized)}</td>
                <td className={pnlClass(p.day_pnl)}>{fmt(p.day_pnl)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ResizableCard>
    </main>
  );
}
