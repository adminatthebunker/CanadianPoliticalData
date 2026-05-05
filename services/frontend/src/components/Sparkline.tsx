interface SparklineProps {
  values: Array<number | null>;
  width?: number;
  height?: number;
  /** Y-axis ceiling. If unset, derived from max(values). Useful to pin
   *  percent metrics to 100 so the spark doesn't rescale every tick. */
  max?: number;
  /** Stroke colour. CSS var allowed. Defaults to admin accent. */
  color?: string;
  /** Optional text shown when no data yet. */
  emptyLabel?: string;
}

/**
 * Minimal SVG sparkline. Pure presentation — handles null gaps by
 * splitting into multiple polyline segments, normalises y to a chosen
 * max, and avoids any external chart-lib dependency. ~40 lines.
 */
export function Sparkline({
  values,
  width = 220,
  height = 36,
  max,
  color = "var(--accent, #79d48d)",
  emptyLabel = "no samples",
}: SparklineProps) {
  if (!values.length) {
    return <span className="admin__muted" style={{ fontSize: ".8rem" }}>{emptyLabel}</span>;
  }
  const numeric = values.filter((v): v is number => v != null && Number.isFinite(v));
  const yMax = max ?? (numeric.length ? Math.max(...numeric) : 1);
  const safeMax = yMax > 0 ? yMax : 1;
  const stepX = values.length > 1 ? width / (values.length - 1) : width;
  const project = (v: number) => height - (v / safeMax) * height;

  // Split into runs separated by nulls so gaps render as breaks.
  const runs: string[] = [];
  let current: string[] = [];
  values.forEach((v, i) => {
    if (v == null || !Number.isFinite(v)) {
      if (current.length) runs.push(current.join(" "));
      current = [];
      return;
    }
    const x = i * stepX;
    const y = project(v);
    current.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  });
  if (current.length) runs.push(current.join(" "));

  return (
    <svg
      role="img"
      aria-label="sparkline"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      style={{ display: "block" }}
    >
      {runs.map((points, i) => (
        <polyline
          key={i}
          points={points}
          fill="none"
          stroke={color}
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      ))}
    </svg>
  );
}
