import { useEffect, useState } from "react";
import { api } from "../api";
import { ResizableCard } from "./ResizableCard";
import { StrategyExperiments } from "./StrategyExperiments";
import { instrumentLabel } from "../markets/display";
import type { CloseloopLibraryRow, CloseloopStatus, CloseloopTraceRow, Position } from "../types";

const POLL_MS = 15_000;

function fmt(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) {
    return "—";
  }
  return n.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function CloseloopPage() {
  const [status, setStatus] = useState<CloseloopStatus | null>(null);
  const [library, setLibrary] = useState<CloseloopLibraryRow[]>([]);
  const [trace, setTrace] = useState<CloseloopTraceRow[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load(opts?: { quiet?: boolean }) {
    try {
      const [st, lib, tr, pos] = await Promise.all([
        api.closeloopStatus(),
        api.closeloopLibrary(),
        api.closeloopTrace(),
        api.positions("cl"),
      ]);
      setStatus(st);
      setLibrary(lib);
      setTrace(tr);
      setPositions(pos);
      setError("");
    } catch (err) {
      if (!opts?.quiet) {
        setError(err instanceof Error ? err.message : String(err));
      }
    }
  }

  useEffect(() => {
    load();
    const timer = window.setInterval(() => load({ quiet: true }).catch(() => undefined), POLL_MS);
    return () => window.clearInterval(timer);
  }, []);

  async function run(fn: () => Promise<CloseloopStatus>) {
    setBusy(true);
    setError("");
    try {
      const next = await fn();
      setStatus(next);
      await load({ quiet: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="research-header">
        <div className="page-heading"><div><p className="eyebrow">STRATEGY RESEARCH</p><h1>因子与模型研究</h1><p>Alpha101 因子账户与模型策略实验分别评估；模型策略当前仅作独立回测。</p></div>
          <div className="research-actions"><span className={`status-pill ${status?.running ? "success" : "neutral"}`}>{status ? status.running ? "研究运行中" : "研究已暂停" : "连接中"}</span>
            <button disabled={busy || !status} onClick={() => run(() => api.closeloopStep())}>{busy ? "处理中…" : "评估下一个因子"}</button>
            <button disabled={busy || !status} onClick={() => run(() => status?.running ? api.closeloopStop() : api.closeloopStart())}>{status?.running ? "暂停研究" : "启动研究"}</button></div>
        </div>
        <div className="research-metrics">
          <div className="metric"><span>数据日期 / 最新覆盖率</span><strong>{status?.data_asof ?? "—"}</strong><small>{status?.latest_coverage == null ? "—" : `${fmt(status.latest_coverage * 100, 1)}%`} · {status?.data_fresh ? "数据有效" : "等待有效数据"}</small></div>
          <div className="metric"><span>最新因子 / 验证门槛</span><strong>{status?.last_alpha ?? "—"}</strong><small>{status?.passed == null ? "等待评估" : status.passed ? "通过" : "未通过 · 不生成交易目标"}</small></div>
          <div className="metric"><span>信息系数 IC / IR</span><strong>{fmt(status?.ic_mean, 4)}</strong><small>IR {fmt(status?.ic_ir, 3)}</small></div>
          <div className="metric"><span>研究账户净值 · {status?.cl_currency ?? "CNY"}</span><strong>{fmt(status?.cl_equity, 0)}</strong><small>现金 {fmt(status?.cl_cash, 0)}</small></div>
        </div>
        {status?.last_error ? <p className="banner error">{status.last_error}</p> : null}
      </div>
      <main className="dashboard research-dashboard">
        {error ? <div className="banner error">{error}</div> : null}
        <StrategyExperiments />
        <ResizableCard id="cl-library" title="因子库" className="wide" minWidth={360} minHeight={220}>
          <table>
            <thead>
              <tr>
                <th>Alpha</th>
                <th>门槛</th>
                <th>IC</th>
                <th>IR</th>
                <th>分组收益差</th>
                <th>换手率</th>
              </tr>
            </thead>
            <tbody>
              {library.length === 0 ? (
                <tr><td colSpan={6}>暂无因子记录，可评估下一个因子。</td></tr>
              ) : library.map((row) => (
                <tr key={row.alpha_id}>
                  <td>{row.alpha_id}</td>
                  <td>{row.passed ? "通过" : "未通过"}</td>
                  <td>{fmt(row.ic_mean, 4)}</td>
                  <td>{fmt(row.ic_ir, 3)}</td>
                  <td>{fmt(row.quantile_spread, 4)}</td>
                  <td>{fmt(row.turnover, 3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ResizableCard>
        <ResizableCard id="cl-trace" title="最近评估记录" className="pane" minWidth={280} minHeight={220}>
          <table>
            <thead>
              <tr>
                <th>Alpha</th>
                <th>门槛</th>
                <th>IC</th>
                <th>评估原因</th>
              </tr>
            </thead>
            <tbody>
              {trace.length === 0 ? (
                <tr><td colSpan={4}>暂无评估记录。</td></tr>
              ) : [...trace].reverse().map((row, i) => (
                <tr key={`${row.alpha_id ?? "row"}-${i}`}>
                  <td>{row.alpha_id ?? "—"}</td>
                  <td>{row.passed ? "通过" : "未通过"}</td>
                  <td>{fmt(row.ic_mean, 4)}</td>
                  <td><details><summary>查看原因</summary><p className="order-reason">{(row.reasons ?? []).join("; ") || "—"}</p></details></td>
                </tr>
              ))}
            </tbody>
          </table>
        </ResizableCard>
        <ResizableCard id="cl-pos" title="研究账户持仓" className="pane" minWidth={240} minHeight={220}>
          <table>
            <thead>
              <tr><th>标的</th><th>数量</th><th>均价</th></tr>
            </thead>
            <tbody>
              {positions.length === 0 ? (
                <tr><td colSpan={3}>暂无持仓。有效行情和验证门槛同时满足才生成模拟订单。</td></tr>
              ) : positions.map((p) => (
                <tr key={`${p.market_id}-${p.symbol}`}>
                  <td>{instrumentLabel(p.market_id, p.symbol, p.name)}</td>
                  <td>{p.quantity}</td>
                  <td>{fmt(p.avg_cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ResizableCard>
      </main>
    </>
  );
}
