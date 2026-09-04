import { useEffect, useState } from "react";
import { api } from "../api";
import { ResizableCard } from "./ResizableCard";
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
      <div className="runner-bar">
        <span className={status?.running ? "live" : "off"}>{status?.running ? "LIVE" : "PAUSED"}</span>
        <span>source {status?.source ?? "—"}</span>
        <span>alpha {status?.last_alpha ?? "—"}</span>
        <span>IC {fmt(status?.ic_mean, 4)} · IR {fmt(status?.ic_ir, 3)}</span>
        <span>CL {fmt(status?.cl_cash, 0)} {status?.cl_currency ?? "CNY"}{status?.cl_equity != null ? ` · eq ${fmt(status.cl_equity, 0)}` : ""}</span>
        <span>
          {status?.can_trade
            ? "dump quotes · may book cl"
            : status?.has_dump === false
              ? "no dump · fixture research, no cl orders"
              : "fixture · no cl orders"}
        </span>
        <span>{status?.last_tick ? `tick ${status.last_tick.replace("T", " ").slice(0, 19)}` : "waiting"}</span>
        <button type="button" disabled={busy} onClick={() => run(() => api.closeloopStep())}>
          Step
        </button>
        {status?.running ? (
          <button type="button" disabled={busy} onClick={() => run(() => api.closeloopStop())}>
            Pause
          </button>
        ) : (
          <button type="button" disabled={busy} onClick={() => run(() => api.closeloopStart())}>
            Start
          </button>
        )}
        {status?.last_error ? <span className="banner error">{status.last_error.split("\n")[0]}</span> : null}
      </div>
      <main className="dashboard">
        {error ? <div className="banner error">{error}</div> : null}
        <ResizableCard id="cl-library" title="Factor library" className="wide" minWidth={360} minHeight={220}>
          <table>
            <thead>
              <tr>
                <th>Alpha</th>
                <th>Passed</th>
                <th>IC</th>
                <th>IR</th>
                <th>Spread</th>
                <th>Turnover</th>
              </tr>
            </thead>
            <tbody>
              {library.length === 0 ? (
                <tr><td colSpan={6}>No library rows. Step once to evaluate an Alpha101 factor.</td></tr>
              ) : library.map((row) => (
                <tr key={row.alpha_id}>
                  <td>{row.alpha_id}</td>
                  <td>{row.passed ? "yes" : "no"}</td>
                  <td>{fmt(row.ic_mean, 4)}</td>
                  <td>{fmt(row.ic_ir, 3)}</td>
                  <td>{fmt(row.quantile_spread, 4)}</td>
                  <td>{fmt(row.turnover, 3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ResizableCard>
        <ResizableCard id="cl-trace" title="Trace" className="pane" minWidth={280} minHeight={220}>
          <table>
            <thead>
              <tr>
                <th>Alpha</th>
                <th>Passed</th>
                <th>IC</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              {trace.length === 0 ? (
                <tr><td colSpan={4}>No trace yet.</td></tr>
              ) : [...trace].reverse().map((row, i) => (
                <tr key={`${row.alpha_id ?? "row"}-${i}`}>
                  <td>{row.alpha_id ?? "—"}</td>
                  <td>{row.passed ? "yes" : "no"}</td>
                  <td>{fmt(row.ic_mean, 4)}</td>
                  <td className="why">{(row.reasons ?? []).join("; ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ResizableCard>
        <ResizableCard id="cl-pos" title="CL positions" className="pane" minWidth={240} minHeight={220}>
          <table>
            <thead>
              <tr><th>Symbol</th><th>Qty</th><th>Avg</th></tr>
            </thead>
            <tbody>
              {positions.length === 0 ? (
                <tr><td colSpan={3}>Flat. Orders only when source is qlib_dump and gates pass.</td></tr>
              ) : positions.map((p) => (
                <tr key={`${p.market_id}-${p.symbol}`}>
                  <td>{p.symbol}</td>
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
