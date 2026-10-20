import { useEffect, useState } from "react";
import { api } from "../api";
import type { StrategyExperimentReport } from "../types";
import { ResizableCard } from "./ResizableCard";

const percent = (n: number | null | undefined) => n == null ? "—" : `${(n * 100).toFixed(2)}%`;
const decimal = (n: number | null | undefined) => n == null ? "—" : n.toFixed(3);

export function StrategyExperiments() {
  const [report, setReport] = useState<StrategyExperimentReport | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const next = await api.strategyExperiments();
        if (active) { setReport(next); setError(""); }
      } catch (err) { if (active) setError(err instanceof Error ? err.message : String(err)); }
    }
    void load();
    const timer = window.setInterval(load, 15000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);
  return <ResizableCard id="strategy-experiments" title="模型策略实验 · 独立影子评估" className="wide">
    <p className="hint">验证集选择持仓、调仓和模型参数，最终留出期按三个窗口滚动训练。每个策略独立回测，尚未接入自动下单。</p>
    {error ? <p className="banner error">{error}</p> : null}
    {!report?.strategies.length ? <p className="empty">尚无完成的策略实验；训练完成后自动显示。</p> : <>
      <div className="experiment-context">
        <span>数据截至 {report.data_asof} · {report.instruments} 只股票</span>
        <span>样本外信号期 {report.test_start} — {report.test_last_signal}</span>
        <span>同期等权对照 {percent(report.benchmark?.net_return)}</span>
      </div>
      {report.benchmark?.stale_valuation_sessions ? <p className="hint">等权对照含 {report.benchmark.stale_valuation_sessions} 个缺价估值日；差距较小的超额收益仍需复核。</p> : null}
      <table>
        <thead><tr>{["策略", "扣费收益", "最大回撤", "夏普", "日均 Rank IC", "双倍成本收益", "研究门槛"].map(h => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{report.strategies.map(row => <tr key={row.id}>
          <td><strong>{row.name}</strong><small className="experiment-subtitle">持仓 {row.portfolio.top_k} · 每 {row.portfolio.rebalance} 日调仓</small></td>
          <td className={(row.test.net_return ?? 0) >= 0 ? "up" : "down"}>{percent(row.test.net_return)}</td>
          <td>{percent(row.test.max_drawdown)}</td><td>{decimal(row.test.sharpe)}</td>
          <td>{decimal(row.ic.rank_ic)}</td><td>{percent(row.double_cost_test.net_return)}</td>
          <td><details><summary>{row.statistical_gate_passed ? "统计通过 · 仍需数据验证" : "未通过 · 查看原因"}</summary>
            <p className="order-reason">{[...row.gate_reasons, ...row.promotion_blockers].join("；")}</p>
            <p>三个窗口扣费收益：{row.folds.map(f => percent(f.net_return)).join(" / ")}</p>
          </details></td>
        </tr>)}</tbody>
      </table>
      <details className="experiment-notes"><summary>数据与回测范围</summary><p>{report.limitations?.join("；")}</p>
        <p>最新排名仅为研究输出，不能视为买卖指令。模型版本：Qlib {report.versions?.qlib} / LightGBM {report.versions?.lightgbm}。</p></details>
    </>}
  </ResizableCard>;
}
