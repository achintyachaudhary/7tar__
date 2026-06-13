/** Theme-aware colors for lightweight-charts.
 *
 * The chart library needs concrete color strings, so CSS variables are
 * resolved from the document at call time. `watchTheme` lets mounted charts
 * restyle live when the user toggles the theme.
 */

export interface ChartColors {
  background: string;
  text: string;
  grid: string;
  up: string;
  down: string;
  upSoft: string;
  downSoft: string;
  accent: string;
  muted: string;
}

function cssVar(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/** 45%-opacity version of a color (volume bars); works for hex and rgb(). */
export function softColor(color: string, alpha = 0.45): string {
  return `color-mix(in srgb, ${color} ${Math.round(alpha * 100)}%, transparent)`;
}

export function getChartColors(): ChartColors {
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  const up = cssVar("--green", dark ? "#2ebd85" : "#089981");
  const down = cssVar("--red", dark ? "#f6465d" : "#d83a52");
  return {
    background: cssVar("--surface", dark ? "#12161f" : "#ffffff"),
    text: cssVar("--text", dark ? "#e7ebf3" : "#18202e"),
    grid: dark ? "rgba(255,255,255,0.05)" : "rgba(16,24,40,0.06)",
    up,
    down,
    upSoft: softColor(up),
    downSoft: softColor(down),
    accent: cssVar("--accent", dark ? "#4c8dff" : "#2563eb"),
    muted: cssVar("--muted", dark ? "#8b95a9" : "#5f6c83"),
  };
}

/** Invoke `onChange` whenever data-theme flips; returns a cleanup function. */
export function watchTheme(onChange: (colors: ChartColors) => void): () => void {
  const observer = new MutationObserver(() => onChange(getChartColors()));
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
  return () => observer.disconnect();
}
