import type { CSSProperties } from "react";

/**
 * Team livery colours, keyed by Jolpica constructorId.
 *
 * `colour` is the broadcast colour (as published by OpenF1 for the 2026 grid). It is
 * used for fills — bars, avatars, strokes — where contrast against the page does not
 * matter. `strong` is the same hue darkened until it clears 4.5:1 on white, for TEXT on
 * the light theme: papaya, teal and light blue all sit under 3:1 on a pale ground, and a
 * name you cannot read is worse than a name in slightly the wrong orange. The dark theme
 * uses `colour` for text as well; the values were checked against the dark panel too.
 *
 * `on` is the ink to place on a `colour` fill (initials in an avatar).
 */
export interface TeamStyle {
  id: string;
  name: string;
  short: string;
  colour: string;
  strong: string;
  on: "#000000" | "#ffffff";
}

export const TEAMS: Record<string, TeamStyle> = {
  mclaren: { id: "mclaren", name: "McLaren", short: "McLaren", colour: "#F47600", strong: "#BC5B00", on: "#000000" },
  mercedes: { id: "mercedes", name: "Mercedes", short: "Mercedes", colour: "#00D7B6", strong: "#008571", on: "#000000" },
  ferrari: { id: "ferrari", name: "Ferrari", short: "Ferrari", colour: "#ED1131", strong: "#E81130", on: "#ffffff" },
  red_bull: { id: "red_bull", name: "Red Bull Racing", short: "Red Bull", colour: "#4781D7", strong: "#3273D2", on: "#ffffff" },
  rb: { id: "rb", name: "Racing Bulls", short: "Racing Bulls", colour: "#6C98FF", strong: "#2A6AFF", on: "#000000" },
  aston_martin: { id: "aston_martin", name: "Aston Martin", short: "Aston Martin", colour: "#229971", strong: "#1D8462", on: "#ffffff" },
  alpine: { id: "alpine", name: "Alpine", short: "Alpine", colour: "#00A1E8", strong: "#007EB5", on: "#000000" },
  williams: { id: "williams", name: "Williams", short: "Williams", colour: "#1868DB", strong: "#1868DB", on: "#ffffff" },
  haas: { id: "haas", name: "Haas F1 Team", short: "Haas", colour: "#9C9FA2", strong: "#73767A", on: "#000000" },
  audi: { id: "audi", name: "Audi", short: "Audi", colour: "#F50537", strong: "#EB0535", on: "#ffffff" },
  cadillac: { id: "cadillac", name: "Cadillac", short: "Cadillac", colour: "#909090", strong: "#767676", on: "#000000" },
};

/** For an id the map does not know — a new entrant — use the neutral clip grey. */
export const NEUTRAL_TEAM: TeamStyle = {
  id: "",
  name: "",
  short: "",
  colour: "#8A8F98",
  strong: "#5F656E",
  on: "#000000",
};

export function teamStyle(id: string | null | undefined): TeamStyle {
  return (id && TEAMS[id]) || NEUTRAL_TEAM;
}

/** Inline custom properties consumed by .team-text / .team-bar / .team-wash in globals.css. */
export function teamVars(id: string | null | undefined): CSSProperties {
  const t = teamStyle(id);
  return {
    "--team": t.colour,
    "--team-strong": t.strong,
    "--team-on": t.on,
  } as CSSProperties;
}
