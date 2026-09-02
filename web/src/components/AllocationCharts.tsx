const PALETTE = ["#4da3ff", "#3dd68c", "#f0c14b", "#c084fc", "#f0616d", "#5eead4", "#fb923c", "#818cf8"];

export type Slice = { label: string; value: number; color: string };

export function colorAt(i: number): string {
  return PALETTE[i % PALETTE.length];
}

function polar(cx: number, cy: number, r: number, angle: number): [number, number] {
  const rad = ((angle - 90) * Math.PI) / 180;
  return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
}

function arc(cx: number, cy: number, r: number, start: number, end: number): string {
  const [x1, y1] = polar(cx, cy, r, end);
  const [x2, y2] = polar(cx, cy, r, start);
  const large = end - start > 180 ? 1 : 0;
  return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 0 ${x2} ${y2}`;
}

export function DonutChart({ slices, empty }: { slices: Slice[]; empty: string }) {
  const total = slices.reduce((sum, s) => sum + s.value, 0);
  if (total <= 0) {
    return <p className="empty">{empty}</p>;
  }
  const cx = 80;
  const cy = 80;
  const r = 62;
  let angle = 0;
  const rings = slices.map((s) => {
    const sweep = (s.value / total) * 360;
    const start = angle;
    const end = angle + sweep;
    angle += sweep;
    return { ...s, sweep, start, end };
  });
  return (
    <div className="donut-wrap">
      <svg viewBox="0 0 160 160" className="donut">
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="#1c2530" strokeWidth="22" />
        {rings.map((s) =>
          s.sweep >= 359.9 ? (
            <circle key={s.label} cx={cx} cy={cy} r={r} fill="none" stroke={s.color} strokeWidth="22" />
          ) : (
            <path key={s.label} d={arc(cx, cy, r, s.start, s.end)} fill="none" stroke={s.color} strokeWidth="22" />
          ),
        )}
      </svg>
      <ul className="legend">
        {slices.map((s) => (
          <li key={s.label}>
            <i style={{ background: s.color }} />
            <span>{s.label}</span>
            <em>{((s.value / total) * 100).toFixed(1)}%</em>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function BarChart({ slices, empty }: { slices: Slice[]; empty: string }) {
  const max = Math.max(0, ...slices.map((s) => s.value));
  if (max <= 0) {
    return <p className="empty">{empty}</p>;
  }
  return (
    <ul className="value-bars">
      {slices.map((s) => (
        <li key={s.label}>
          <span className="bar-label">{s.label}</span>
          <span className="bar-track">
            <span className="bar-fill" style={{ width: `${(s.value / max) * 100}%`, background: s.color }} />
          </span>
          <span className="bar-value">
            {s.value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </span>
        </li>
      ))}
    </ul>
  );
}
