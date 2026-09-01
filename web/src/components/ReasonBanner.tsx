import type { Signal } from "../types";

export function ReasonBanner({ signals }: { signals: Signal[] }) {
  if (!signals.length) {
    return null;
  }
  return (
    <div className="reason-banner">
      <div className="reason-chips">
        {signals.map((s) => (
          <div key={s.strategy_id} className={`reason-chip ${s.action}`} title={s.reason}>
            <span className="chip-name">{s.name}</span>
            <span className="chip-action">{s.action}</span>
            <span className="chip-reason">{s.reason}</span>
          </div>
        ))}
      </div>
    </div>
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
