"use client";

import { useMemo, useState } from "react";
import { money, pct, seriesColor } from "@/lib/format";

export type ChartPoint = {
  key: string;
  label: string;
  cost: number;
  quality: number;
  success: number | null;
  recommended?: boolean;
  baseline?: boolean;
  meets?: boolean;
};

const W = 640;
const H = 400;
const M = { top: 24, right: 28, bottom: 48, left: 52 };

function niceMax(v: number): number {
  if (v <= 0) return 0.01;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / p;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10;
  return step * p;
}

export function CostQualityChart({ points }: { points: ChartPoint[] }) {
  const [hover, setHover] = useState<ChartPoint | null>(null);
  const layout = useMemo(() => {
    const maxCost = niceMax(Math.max(...points.map((p) => p.cost), 0.001) * 1.2);
    const minQ = Math.max(0, Math.floor((Math.min(...points.map((p) => p.quality), 100) - 8) / 10) * 10);
    const x = (c: number) => M.left + (c / maxCost) * (W - M.left - M.right);
    const y = (q: number) => M.top + (1 - (q - minQ) / (100 - minQ)) * (H - M.top - M.bottom);
    const xTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * maxCost);
    const yTicks: number[] = [];
    for (let q = minQ; q <= 100; q += 10) yTicks.push(q);
    // direct labels: right of the point unless it would overflow; nudge vertical collisions
    const placed = points
      .map((p) => ({ p, px: x(p.cost), py: y(p.quality) }))
      .sort((a, b) => a.py - b.py)
      .map((d) => ({ ...d, right: d.px + 150 < W - M.right, ly: d.py + 4 }));
    for (let i = 1; i < placed.length; i++) {
      const prev = placed[i - 1];
      const cur = placed[i];
      if (Math.abs(cur.ly - prev.ly) < 16 && Math.abs(cur.px - prev.px) < 140 && cur.right === prev.right) cur.ly = prev.ly + 16;
    }
    return { x, y, xTicks, yTicks, placed, maxCost, minQ };
  }, [points]);

  return (
    <div className="chart-wrap">
      <div className="chart">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Cost per run against quality score, one point per option">
          <g className="grid">
            {layout.yTicks.map((q) => (
              <line key={q} x1={M.left} x2={W - M.right} y1={layout.y(q)} y2={layout.y(q)} />
            ))}
          </g>
          <g className="axis">
            <line x1={M.left} x2={W - M.right} y1={H - M.bottom} y2={H - M.bottom} />
            <line x1={M.left} x2={M.left} y1={M.top} y2={H - M.bottom} />
          </g>
          {layout.xTicks.map((c) => (
            <text key={c} className="tick" x={layout.x(c)} y={H - M.bottom + 18} textAnchor="middle">
              {money(c, c < 0.01 ? 4 : 3)}
            </text>
          ))}
          {layout.yTicks.map((q) => (
            <text key={q} className="tick" x={M.left - 8} y={layout.y(q) + 4} textAnchor="end">
              {q}
            </text>
          ))}
          <text className="axis-label" x={W - M.right} y={H - 8} textAnchor="end">
            Cost per run, USD
          </text>
          <text className="axis-label" x={M.left} y={M.top - 10}>
            Quality, judge score 0–100
          </text>
          {layout.placed.map(({ p, px, py, right, ly }) => (
            <g key={p.key}>
              {p.recommended && <circle cx={px} cy={py} r={12} fill="none" stroke="var(--ink)" strokeWidth={1.5} />}
              {p.baseline ? (
                <circle cx={px} cy={py} r={6} fill="var(--surface)" stroke={seriesColor(p.key)} strokeWidth={2.5} />
              ) : (
                <circle cx={px} cy={py} r={6.5} fill={seriesColor(p.key)} stroke="var(--surface)" strokeWidth={2} />
              )}
              <text className="label" x={right ? px + 16 : px - 16} y={ly} textAnchor={right ? "start" : "end"}>
                {p.label}
                {p.recommended && <tspan className="sublabel"> · recommended</tspan>}
              </text>
              <circle
                className="hit"
                cx={px}
                cy={py}
                r={18}
                tabIndex={0}
                aria-label={`${p.label}: cost ${money(p.cost)} per run, quality ${p.quality}`}
                onMouseEnter={() => setHover(p)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(p)}
                onBlur={() => setHover(null)}
              />
            </g>
          ))}
        </svg>
      </div>
      {hover && (
        <div className="tooltip" style={{ left: `${(layout.x(hover.cost) / W) * 100}%`, top: `${(layout.y(hover.quality) / H) * 100}%` }}>
          <b>{hover.label}</b>
          <br />
          quality {hover.quality} · success {pct(hover.success)}
          <br />
          {money(hover.cost)} per run
        </div>
      )}
    </div>
  );
}
