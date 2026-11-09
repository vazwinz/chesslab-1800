/** @type {import('tailwindcss').Config} */
const c = (v) => `rgb(var(--${v}) / <alpha-value>)`;
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: c("paper"),
        sheet: c("sheet"),
        sunk: c("sunk"),
        ink: c("ink"),
        muted: c("muted"),
        faint: c("faint"),
        rule: c("rule"),
        pen: c("pen"),
        "pen-ink": c("pen-ink"),
        good: c("good"),
        bad: c("bad"),
        warn: c("warn"),
      },
      fontFamily: {
        sans: ['"Atkinson Hyperlegible Next Variable"', "system-ui", "Segoe UI", "Roboto", "sans-serif"],
        figurine: ['"Segoe UI Symbol"', '"Noto Sans Symbols 2"', '"DejaVu Sans"', "sans-serif"],
      },
      fontSize: {
        xs: ["0.8125rem", { lineHeight: "1.15rem" }],
        sm: ["0.875rem", { lineHeight: "1.3rem" }],
        base: ["1rem", { lineHeight: "1.55rem" }],
        lg: ["1.25rem", { lineHeight: "1.75rem" }],
        xl: ["1.5625rem", { lineHeight: "2rem" }],
        "2xl": ["1.953rem", { lineHeight: "2.3rem" }],
        "3xl": ["2.441rem", { lineHeight: "2.7rem" }],
      },
      maxWidth: { prose: "68ch" },
    },
  },
  plugins: [],
};
