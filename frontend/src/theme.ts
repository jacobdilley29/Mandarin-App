// Design tokens mirrored from DESIGN.md for use in TS (e.g. SVG fills that
// can't read CSS variables directly). Keep in sync with src/index.css.

export const tokens = {
  light: {
    bg: "#F6F4EC",
    surface: "#FFFFFF",
    ink: "#1E2A24",
    inkSoft: "#5B6B62",
    inkFaint: "#8A968D",
    primary: "#00694E",
    accent: "#C8352A",
    good: "#2E7D5B",
    warn: "#B8791B",
    bad: "#C8352A",
  },
  dark: {
    bg: "#121714",
    surface: "#1A211D",
    ink: "#ECF1ED",
    inkSoft: "#A5B3AB",
    inkFaint: "#6E7C74",
    primary: "#3FB08A",
    accent: "#E86A5E",
    good: "#4FBF8B",
    warn: "#D69A3E",
    bad: "#E86A5E",
  },
} as const;

export type ThemePref = "system" | "light" | "dark";

/** Apply the theme preference to <html> so CSS variables resolve correctly. */
export function applyTheme(pref: ThemePref): void {
  const root = document.documentElement;
  if (pref === "system") {
    root.removeAttribute("data-theme");
  } else {
    root.setAttribute("data-theme", pref);
  }
}
