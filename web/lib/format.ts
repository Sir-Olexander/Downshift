export const SERIES: Record<string, { label: string; color: string; short: string }> = {
  baseline: { label: "Baseline · Nemotron 3 Ultra", short: "Baseline", color: "var(--s-baseline)" },
  super: { label: "Nemotron 3 Super", short: "Super", color: "var(--s-super)" },
  nano: { label: "Nemotron 3 Nano", short: "Nano", color: "var(--s-nano)" },
  mix: { label: "Per-step mix", short: "Mix", color: "var(--s-mix)" },
};

export function seriesColor(key: string): string {
  return SERIES[key]?.color ?? "var(--ink-3)";
}

export function money(x: number | null | undefined, digits = 4): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  return `$${x.toFixed(digits)}`;
}

export function pct(x: number | null | undefined, digits = 0): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  return `${x.toFixed(digits)}%`;
}

export function signed(x: number | null | undefined, digits = 0, suffix = ""): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  const s = x > 0 ? "+" : x < 0 ? "−" : "±";
  return `${s}${Math.abs(x).toFixed(digits)}${suffix}`;
}

export function seconds(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "–";
  return ms >= 10000 ? `${Math.round(ms / 1000)} s` : `${(ms / 1000).toFixed(1)} s`;
}

export function compact(n: number | null | undefined): string {
  if (n === null || n === undefined) return "–";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000) return `${Math.round(n / 1000)}K`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

export function shortModel(id: string | undefined | null): string {
  if (!id) return "–";
  return id.replace("nemotron-3-", "N3 ").replace(/^N3 (\w)/, (_, c: string) => `N3 ${c.toUpperCase()}`);
}

export function when(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function clock(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/** Direction-aware class for a delta: `upGood` says whether a higher value is better. */
export function deltaClass(x: number | null | undefined, upGood: boolean, deadband = 0.5): string {
  if (x === null || x === undefined) return "flat";
  if (Math.abs(x) <= deadband) return "flat";
  return (x > 0) === upGood ? "good" : "bad";
}
