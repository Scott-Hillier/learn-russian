import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

function usePrefersDark(): boolean {
  const query = "(prefers-color-scheme: dark)";
  const [dark, setDark] = useState(() => window.matchMedia?.(query).matches ?? false);
  useEffect(() => {
    const mq = window.matchMedia?.(query);
    if (!mq) return;
    const onChange = () => setDark(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return dark;
}

/* Chart conventions (see the dataviz method): 2px lines, >=8px markers with a 2px surface ring,
   columns <=24px with 4px rounded data-ends and a 2px surface gap between stacked segments,
   hairline solid gridlines, text in ink tokens (never series colours), a legend for 2+ series,
   and a hover tooltip on every plotted chart. Colours come from --viz-* CSS variables. */

const W = 640;

function niceStep(range: number, target = 4): number {
  const raw = range / target;
  const mag = 10 ** Math.floor(Math.log10(raw || 1));
  const n = raw / mag;
  return (n >= 5 ? 10 : n >= 2 ? 5 : n >= 1 ? 2 : 1) * mag;
}

function ticks(min: number, max: number, target = 4): number[] {
  const step = niceStep(max - min, target);
  const out = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(Math.round(v * 100) / 100);
  return out;
}

/** Split a series with nulls into drawable path segments. */
function segments(values: (number | null)[], x: (i: number) => number, y: (v: number) => number): string[] {
  const paths: string[] = [];
  let d = "";
  values.forEach((v, i) => {
    if (v === null) {
      if (d) paths.push(d);
      d = "";
    } else d += `${d ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
  });
  if (d) paths.push(d);
  return paths;
}

function Tooltip({ x, y, children, containerWidth }: { x: number; y: number; children: ReactNode; containerWidth: number }) {
  const flip = x > containerWidth * 0.65;
  return (
    <div className="viz-tooltip" style={{ left: flip ? undefined : x + 12, right: flip ? containerWidth - x + 12 : undefined, top: y }}>
      {children}
    </div>
  );
}

function useHover() {
  const ref = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ index: number; px: number; py: number } | null>(null);
  return { ref, hover, setHover };
}

function LegendKey({ series }: { series: { label: string; className: string; kind: "line" | "box" }[] }) {
  return (
    <div className="viz-legend">
      {series.map((s) => (
        <span key={s.label}>
          <svg width="16" height="10" aria-hidden>
            {s.kind === "line" ? (
              <line x1="1" x2="15" y1="5" y2="5" className={`${s.className} viz-line`} />
            ) : (
              <rect x="2" y="0" width="10" height="10" rx="2" className={s.className} />
            )}
          </svg>
          {s.label}
        </span>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- Intonation */

interface IntonationProps {
  native: (number | null)[];
  yours: (number | null)[];
  marks: { position: number; label: string }[];
}

export function IntonationChart({ native, yours, marks }: IntonationProps) {
  const H = 190;
  const pad = { l: 40, r: 16, t: 26, b: 26 };
  const { ref, hover, setHover } = useHover();
  const all = [...native, ...yours].filter((v): v is number => v !== null);
  const lo = Math.min(-3, Math.floor(Math.min(...all)));
  const hi = Math.max(3, Math.ceil(Math.max(...all)));
  const n = Math.max(native.length, yours.length);
  const x = (i: number) => pad.l + (i / Math.max(1, n - 1)) * (W - pad.l - pad.r);
  const y = (v: number) => pad.t + ((hi - v) / (hi - lo)) * (H - pad.t - pad.b);
  const yTicks = ticks(lo, hi, 3);
  const lastValue = (s: (number | null)[]) => {
    for (let i = s.length - 1; i >= 0; i--) if (s[i] !== null) return { i, v: s[i] as number };
    return null;
  };
  const ends = [
    { key: "native", end: lastValue(native) },
    { key: "yours", end: lastValue(yours) },
  ];

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const sx = ((e.clientX - box.left) / box.width) * W;
    const index = Math.round(((sx - pad.l) / (W - pad.l - pad.r)) * (n - 1));
    if (index < 0 || index >= n) return setHover(null);
    setHover({ index, px: e.clientX - box.left, py: e.clientY - box.top });
  };
  const fmt = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)} st`);

  return (
    <figure className="viz" ref={ref}>
      <figcaption>
        <strong>Intonation</strong>
        <span className="muted"> · pitch from start to end of the phrase, relative to each voice's usual pitch</span>
      </figcaption>
      <LegendKey
        series={[
          { label: "Native voice", className: "viz-s1", kind: "line" },
          { label: "You", className: "viz-s2", kind: "line" },
        ]}
      />
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="viz-svg"
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
        role="img"
        aria-label="Pitch contour of the native voice and your recording"
      >
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} className={t === 0 ? "viz-baseline" : "viz-grid"} />
            <text x={pad.l - 8} y={y(t) + 4} textAnchor="end" className="viz-tick">
              {t > 0 ? `+${t}` : t}
            </text>
          </g>
        ))}
        {marks.map((m, i) => {
          const mx = pad.l + m.position * (W - pad.l - pad.r);
          return (
            <g key={i}>
              <line x1={mx} x2={mx} y1={pad.t - 6} y2={H - pad.b} className="viz-grid" />
              <text x={mx} y={pad.t - 10} textAnchor="middle" className="viz-mark-label" lang="ru">
                {m.label}
                {"́"}
              </text>
            </g>
          );
        })}
        <text x={pad.l} y={H - 6} className="viz-tick">
          start
        </text>
        <text x={W - pad.r} y={H - 6} textAnchor="end" className="viz-tick">
          end
        </text>
        {segments(native, x, y).map((d, i) => (
          <path key={`n${i}`} d={d} className="viz-s1 viz-line" />
        ))}
        {segments(yours, x, y).map((d, i) => (
          <path key={`y${i}`} d={d} className="viz-s2 viz-line" />
        ))}
        {ends.map(
          ({ key, end }) =>
            end && <circle key={key} cx={x(end.i)} cy={y(end.v)} r="4" className={`${key === "native" ? "viz-s1" : "viz-s2"} viz-dot`} />,
        )}
        {hover && <line x1={x(hover.index)} x2={x(hover.index)} y1={pad.t} y2={H - pad.b} className="viz-crosshair" />}
      </svg>
      {hover && (
        <Tooltip x={hover.px} y={hover.py} containerWidth={ref.current?.clientWidth ?? W}>
          <div>
            <b>{fmt(native[hover.index])}</b> <span className="muted">Native voice</span>
          </div>
          <div>
            <b>{fmt(yours[hover.index])}</b> <span className="muted">You</span>
          </div>
        </Tooltip>
      )}
      <p className="viz-note">
        Marked letters are the stressed syllables. Try to rise and fall in the same places as the native voice.
      </p>
    </figure>
  );
}

/* ---------------------------------------------------------------- Daily activity */

export interface DailyPoint {
  date: string; // YYYY-MM-DD
  attempts: number;
  reviews: number;
  average_score: number | null;
}

const shortDate = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

export function ActivityChart({ days }: { days: DailyPoint[] }) {
  const H = 200;
  const pad = { l: 36, r: 12, t: 12, b: 26 };
  const { ref, hover, setHover } = useHover();
  const max = Math.max(4, ...days.map((d) => d.attempts + d.reviews));
  const yTicks = ticks(0, max, 3);
  const top = yTicks[yTicks.length - 1] < max ? max : yTicks[yTicks.length - 1];
  const band = (W - pad.l - pad.r) / days.length;
  const bw = Math.min(24, band - 4);
  const y = (v: number) => pad.t + (1 - v / top) * (H - pad.t - pad.b);
  const base = y(0);
  const GAP = 2;

  // Column with rounded data-end only (square at the baseline).
  const column = (x0: number, y0: number, y1: number, rounded: boolean) => {
    const h = y1 - y0;
    if (h <= 0) return "";
    const r = rounded ? Math.min(4, h, bw / 2) : 0;
    return `M${x0},${y1}V${y0 + r}Q${x0},${y0} ${x0 + r},${y0}H${x0 + bw - r}Q${x0 + bw},${y0} ${x0 + bw},${y0 + r}V${y1}Z`;
  };

  return (
    <figure className="viz" ref={ref}>
      <figcaption>
        <strong>Daily practice</strong>
        <span className="muted"> · last {days.length} days</span>
      </figcaption>
      <LegendKey
        series={[
          { label: "Speaking attempts", className: "viz-s1", kind: "box" },
          { label: "Flashcard reviews", className: "viz-s2", kind: "box" },
        ]}
      />
      <svg viewBox={`0 0 ${W} ${H}`} className="viz-svg" role="img" aria-label="Speaking attempts and flashcard reviews per day">
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} className={t === 0 ? "viz-baseline" : "viz-grid"} />
            <text x={pad.l - 8} y={y(t) + 4} textAnchor="end" className="viz-tick">
              {t}
            </text>
          </g>
        ))}
        {days.map((d, i) => {
          const x0 = pad.l + i * band + (band - bw) / 2;
          const attemptsTop = y(d.attempts);
          const hasReviews = d.reviews > 0;
          const reviewsBottom = d.attempts > 0 ? attemptsTop - GAP : base;
          return (
            <g
              key={d.date}
              onPointerEnter={(e) => {
                const box = ref.current!.getBoundingClientRect();
                setHover({ index: i, px: e.clientX - box.left, py: e.clientY - box.top });
              }}
              onPointerLeave={() => setHover(null)}
            >
              <rect x={pad.l + i * band} y={pad.t} width={band} height={H - pad.t - pad.b} fill="transparent" />
              {d.attempts > 0 && <path d={column(x0, attemptsTop, base, !hasReviews)} className="viz-s1" />}
              {hasReviews && (
                <path d={column(x0, reviewsBottom - (base - y(d.reviews)), reviewsBottom, true)} className="viz-s2" />
              )}
            </g>
          );
        })}
        {[0, Math.floor(days.length / 2), days.length - 1].map((i) => (
          <text
            key={i}
            x={pad.l + i * band + band / 2}
            y={H - 6}
            textAnchor={i === 0 ? "start" : i === days.length - 1 ? "end" : "middle"}
            className="viz-tick"
          >
            {shortDate(days[i].date)}
          </text>
        ))}
      </svg>
      {hover && (
        <Tooltip x={hover.px} y={hover.py} containerWidth={ref.current?.clientWidth ?? W}>
          <div className="muted">{shortDate(days[hover.index].date)}</div>
          <div>
            <b>{days[hover.index].attempts}</b> <span className="muted">speaking attempts</span>
          </div>
          <div>
            <b>{days[hover.index].reviews}</b> <span className="muted">flashcard reviews</span>
          </div>
        </Tooltip>
      )}
    </figure>
  );
}

export function ScoreChart({ days }: { days: DailyPoint[] }) {
  const H = 160;
  const pad = { l: 36, r: 12, t: 12, b: 26 };
  const { ref, hover, setHover } = useHover();
  const n = days.length;
  const x = (i: number) => pad.l + (i + 0.5) * ((W - pad.l - pad.r) / n);
  const y = (v: number) => pad.t + (1 - v / 100) * (H - pad.t - pad.b);
  const values = days.map((d) => d.average_score);

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const sx = ((e.clientX - box.left) / box.width) * W;
    const index = Math.floor(((sx - pad.l) / (W - pad.l - pad.r)) * n);
    if (index < 0 || index >= n) return setHover(null);
    setHover({ index, px: e.clientX - box.left, py: e.clientY - box.top });
  };

  return (
    <figure className="viz" ref={ref}>
      <figcaption>
        <strong>Average pronunciation score</strong>
        <span className="muted"> · per day with speaking practice</span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="viz-svg" onPointerMove={onMove} onPointerLeave={() => setHover(null)} role="img" aria-label="Average pronunciation score per day">
        {[0, 50, 100].map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} className={t === 0 ? "viz-baseline" : "viz-grid"} />
            <text x={pad.l - 8} y={y(t) + 4} textAnchor="end" className="viz-tick">
              {t}%
            </text>
          </g>
        ))}
        {segments(values, x, y).map((d, i) => (
          <path key={i} d={d} className="viz-s1 viz-line" />
        ))}
        {values.map((v, i) => v !== null && <circle key={i} cx={x(i)} cy={y(v)} r="4" className="viz-s1 viz-dot" />)}
        {hover && <line x1={x(hover.index)} x2={x(hover.index)} y1={pad.t} y2={H - pad.b} className="viz-crosshair" />}
        {[0, n - 1].map((i) => (
          <text key={i} x={x(i)} y={H - 6} textAnchor={i === 0 ? "start" : "end"} className="viz-tick">
            {shortDate(days[i].date)}
          </text>
        ))}
      </svg>
      {hover && (
        <Tooltip x={hover.px} y={hover.py} containerWidth={ref.current?.clientWidth ?? W}>
          <div className="muted">{shortDate(days[hover.index].date)}</div>
          <div>
            <b>{values[hover.index] === null ? "No practice" : `${values[hover.index]}%`}</b>
          </div>
        </Tooltip>
      )}
    </figure>
  );
}

/* ---------------------------------------------------------------- Letter heatmap */

// Sequential single-hue blue ramp (steps 100→700), light → dark for "weaker → stronger".
const RAMP = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"];
const DARK_TEXT_UNTIL = 6; // ramp index from which white text clears contrast

export function LetterHeatmap({
  letters,
  stats,
  onPick,
}: {
  letters: string[];
  stats: Record<string, { average: number; count: number }>;
  onPick?: (letter: string) => void;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const dark = usePrefersDark();
  // On a dark surface the ramp runs the other way, so stronger letters stay the most prominent.
  const colour = (step: number) => {
    const i = dark ? RAMP.length - 1 - step : step;
    return { background: RAMP[i], color: i >= DARK_TEXT_UNTIL ? "#ffffff" : "#0b0b0b" };
  };
  const cells = useMemo(
    () =>
      letters.map((l) => {
        const s = stats[l];
        if (!s) return { letter: l, s: null, step: -1 };
        return { letter: l, s, step: Math.min(RAMP.length - 1, Math.floor(s.average * RAMP.length)) };
      }),
    [letters, stats],
  );
  const hovered = cells.find((c) => c.letter === hover);

  return (
    <figure className="viz">
      <figcaption>
        <strong>How clearly you say each letter</strong>
        <span className="muted"> · average of your recent attempts</span>
      </figcaption>
      <div className="heatmap" onPointerLeave={() => setHover(null)}>
        {cells.map((c) => (
          <button
            key={c.letter}
            className={`heat-cell${c.s ? "" : " empty"}`}
            style={c.s ? colour(c.step) : undefined}
            onPointerEnter={() => setHover(c.letter)}
            onFocus={() => setHover(c.letter)}
            onClick={() => onPick?.(c.letter)}
            aria-label={c.s ? `${c.letter}: ${Math.round(c.s.average * 100)}% over ${c.s.count} attempts` : `${c.letter}: not practised`}
            lang="ru"
          >
            {c.letter}
          </button>
        ))}
      </div>
      <div className="heat-legend">
        <span className="muted">weaker</span>
        <span className="heat-ramp" style={{ background: `linear-gradient(to right, ${(dark ? [...RAMP].reverse() : RAMP).join(",")})` }} />
        <span className="muted">stronger</span>
        <span className="heat-cell empty small" aria-hidden />
        <span className="muted">not practised</span>
      </div>
      <p className="viz-readout" aria-live="polite">
        {hovered ? (
          hovered.s ? (
            <>
              <b lang="ru">{hovered.letter}</b> <b>{Math.round(hovered.s.average * 100)}%</b>{" "}
              <span className="muted">over {hovered.s.count} scored occurrences</span>
            </>
          ) : (
            <>
              <b lang="ru">{hovered.letter}</b> <span className="muted">not practised yet</span>
            </>
          )
        ) : (
          <span className="muted">Hover or tab to a letter for its score.</span>
        )}
      </p>
    </figure>
  );
}
