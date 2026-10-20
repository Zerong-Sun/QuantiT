import type { Signal } from "../types";

export function ReasonBanner({ signals }: { signals: Signal[] }) {
  if (!signals.length) {
    return null;
  }
  return (
    <details className="reason-banner">
      <summary>个股参考信号 <span>{signals.length} 项 · 展开查看依据</span></summary>
      <p className="hint">组合调仓以当前策略账户的规则为准。</p>
      <div className="reason-chips">
        {signals.map((s) => (
          <div key={s.strategy_id} className={`reason-chip ${s.action}`} title={s.reason}>
            <span className="chip-name">{s.name}</span>
            <span className="chip-action">{s.action}</span>
            <span className="chip-reason">{s.reason}</span>
          </div>
        ))}
      </div>
    </details>
  );
}

export function signalRationale(signals: Signal[], side: "buy" | "sell"): string {
  const matching = signals.filter((s) => s.action === side);
  if (matching.length) {
    return matching.map((s) => `${s.name}: ${s.reason}`).join("\n");
  }
  const snapshot = signals.map((s) => `${s.name}=${s.action}`).join(", ");
  return `Manual ${side}${snapshot ? `; strategies were ${snapshot}` : "; no strategy wired"}.`;
}
