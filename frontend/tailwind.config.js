/** @type {import('tailwindcss').Config} */
// Colours reference CSS custom properties (defined in src/index.css) so light
// and dark themes come from one token set. See DESIGN.md.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        border: "var(--border)",
        ink: "var(--ink)",
        "ink-soft": "var(--ink-soft)",
        "ink-faint": "var(--ink-faint)",
        primary: "var(--primary)",
        "primary-ink": "var(--primary-ink)",
        "primary-soft": "var(--primary-soft)",
        accent: "var(--accent)",
        "accent-soft": "var(--accent-soft)",
        good: "var(--good)",
        warn: "var(--warn)",
        bad: "var(--bad)",
      },
      fontFamily: {
        serifhan: ['"Noto Serif TC"', "serif"],
        han: ['"Noto Sans TC"', "sans-serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      fontSize: {
        hero: ["4rem", { lineHeight: "1.1" }],
        "hero-lg": ["5.5rem", { lineHeight: "1.05" }],
      },
      borderRadius: {
        md: "12px",
        lg: "18px",
      },
      boxShadow: {
        card: "0 1px 2px rgba(30,42,36,.06), 0 8px 24px rgba(30,42,36,.06)",
      },
    },
  },
  plugins: [],
};
