"use client";

/** Custom SVG box plot — renders min/Q1/median/Q3/max + outliers.
 * No external chart library; ~90 lines of SVG. */

interface BoxPlotProps {
  data: {
    min: number;
    q1: number;
    median: number;
    q3: number;
    max: number;
    outliers: { unit_price: number; contract_no?: string }[];
  } | null;
}

const W = 600;
const H = 220;
const PAD_L = 60;
const PAD_R = 40;
const PAD_T = 30;
const PAD_B = 30;
const PLOT_W = W - PAD_L - PAD_R;
const PLOT_H = H - PAD_T - PAD_B;

export function BoxPlot({ data }: BoxPlotProps) {
  if (!data) {
    return (
      <div className="flex h-[220px] items-center justify-center text-sm text-muted-foreground">
        无已校验价格数据
      </div>
    );
  }

  const { min, q1, median, q3, max, outliers } = data;
  const range = max - min || 1;
  // include outliers in scale
  const allVals = [min, max, ...outliers.map((o) => o.unit_price)];
  const scaleMin = Math.min(...allVals);
  const scaleMax = Math.max(...allVals);
  const scaleRange = scaleMax - scaleMin || 1;

  const y = (val: number) => PAD_T + PLOT_H - ((val - scaleMin) / scaleRange) * PLOT_H;
  const cx = W / 2;
  const boxHalf = 60;

  const gridVals = [];
  const steps = 4;
  for (let i = 0; i <= steps; i++) {
    const v = scaleMin + (scaleRange * i) / steps;
    gridVals.push(v);
  }

  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`}>
      <defs>
        <linearGradient id="bp-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--color-primary, #3b82f6)" stopOpacity="0.25" />
          <stop offset="100%" stopColor="var(--color-primary, #3b82f6)" stopOpacity="0.05" />
        </linearGradient>
      </defs>

      {/* Grid lines + Y labels */}
      {gridVals.map((v, i) => (
        <g key={i}>
          <line x1={PAD_L} y1={y(v)} x2={W - PAD_R} y2={y(v)} stroke="currentColor" strokeWidth={1} strokeDasharray="2 4" opacity={0.22} />
          <text x={8} y={y(v) + 4} fill="currentColor" fontSize={12} opacity={0.65} fontFamily="monospace">
            ¥{v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(0)}
          </text>
        </g>
      ))}

      {/* Whiskers */}
      <line x1={cx} y1={y(max)} x2={cx} y2={y(q3)} stroke="currentColor" strokeWidth={1.5} opacity={0.45} />
      <line x1={cx} y1={y(min)} x2={cx} y2={y(q1)} stroke="currentColor" strokeWidth={1.5} opacity={0.45} />
      <line x1={cx - 25} y1={y(max)} x2={cx + 25} y2={y(max)} stroke="currentColor" strokeWidth={2} opacity={0.55} />
      <line x1={cx - 25} y1={y(min)} x2={cx + 25} y2={y(min)} stroke="currentColor" strokeWidth={2} opacity={0.55} />

      {/* Box (Q1 → Q3) */}
      <rect
        x={cx - boxHalf}
        y={y(q3)}
        width={boxHalf * 2}
        height={Math.max(y(q1) - y(q3), 4)}
        fill="url(#bp-grad)"
        stroke="var(--color-primary, #3b82f6)"
        strokeWidth={1.5}
        rx={6}
      />

      {/* Median line */}
      <line
        x1={cx - boxHalf}
        y1={y(median)}
        x2={cx + boxHalf}
        y2={y(median)}
        stroke="var(--color-primary, #3b82f6)"
        strokeWidth={3}
        strokeLinecap="round"
      />

      {/* Outliers */}
      {outliers.map((o, i) => (
        <g key={i}>
          <circle cx={cx} cy={y(o.unit_price)} r={5} fill="#f43f5e" stroke="var(--background, #fff)" strokeWidth={2} />
          <text x={cx + 14} y={y(o.unit_price) + 4} fill="#f43f5e" fontSize={10} fontWeight={600}>
            ¥{o.unit_price.toFixed(0)}
          </text>
        </g>
      ))}

      {/* Labels */}
      <text x={cx - boxHalf - 8} y={y(q1) + 4} textAnchor="end" fill="currentColor" fontSize={12} opacity={0.7}>
        Q1 ¥{q1.toFixed(0)}
      </text>
      <text x={cx} y={H - 8} textAnchor="middle" fill="var(--color-primary, #3b82f6)" fontSize={12} fontWeight={700}>
        中位 ¥{median.toFixed(0)}
      </text>
      <text x={cx + boxHalf + 8} y={y(q3) + 4} fill="currentColor" fontSize={12} opacity={0.7}>
        Q3 ¥{q3.toFixed(0)}
      </text>
      <text x={cx - boxHalf - 8} y={y(max) + 4} textAnchor="end" fill="currentColor" fontSize={11} opacity={0.6}>
        max ¥{max.toFixed(0)}
      </text>
      <text x={cx + boxHalf + 8} y={y(min) + 4} fill="currentColor" fontSize={11} opacity={0.6}>
        min ¥{min.toFixed(0)}
      </text>
    </svg>
  );
}
