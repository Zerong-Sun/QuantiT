import type { Strategy } from "../types";

function fmtParam(value: string | number | boolean | null): string {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  return String(value);
}

export function StrategyDesk({
  strategies,
  selectedId,
  onSelect,
  market,
}: {
  strategies: Strategy[];
  selectedId: string;
  onSelect: (id: string) => void;
  market: string;
}) {
  const selected = strategies.find((s) => s.id === selectedId) ?? strategies[0];
  if (!selected) {
    return <p className="empty">No strategies registered.</p>;
  }
  return (
    <div className="strategy-desk">
      <div className="strategy-tabs">
        {strategies.map((s) => {
          const applies = s.markets.includes(market);
          return (
            <button
              key={s.id}
              className={`${s.id === selected.id ? "active" : ""} ${applies ? "" : "dim"}`}
              onClick={() => onSelect(s.id)}
            >
              {s.name}
              <small>{s.markets.join(" / ").toUpperCase()}</small>
            </button>
          );
        })}
      </div>
      <div className="strategy-body">
        <header>
          <div>
            <h3>{selected.name}</h3>
            <p className="meta">
              {selected.class_name} · {selected.horizon}
              {selected.markets.includes(market) ? " · applies to this market" : " · other market"}
            </p>
          </div>
        </header>
        <p className="thesis">{selected.thesis}</p>
        <h4>Rules</h4>
        <ol className="rules">
          {selected.rules.map((rule) => (
            <li key={rule}>{rule}</li>
          ))}
        </ol>
        <h4>Parameters</h4>
        <p className="hint">Live defaults from the Python strategy class. Changing the class updates this table.</p>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Value</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {selected.parameters.map((p) => (
              <tr key={p.name}>
                <td><code>{p.name}</code></td>
                <td>{fmtParam(p.value)}</td>
                <td>{p.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {selected.score_weights ? (
          <>
            <h4>Score mix</h4>
            <p className="weights">
              {Object.entries(selected.score_weights).map(([k, v]) => (
                <span key={k}>{k} {(v * 100).toFixed(0)}%</span>
              ))}
            </p>
          </>
        ) : null}
        {selected.universe ? (
          <>
            <h4>Universe</h4>
            <div className="universe">
              {Object.entries(selected.universe).map(([theme, members]) => (
                <div key={theme} className="sleeve">
                  <h5>{theme}</h5>
                  <ul>
                    {members.map((m) => (
                      <li key={m.symbol}>
                        <code>{m.symbol}</code> {m.name}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
