/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#111214", 900: "#16181b", 850: "#1b1d21", 800: "#202328", 700: "#2a2e34", 600: "#3a3f47", 400: "#8a919c", 300: "#b5bbc4", 100: "#e8eaed" },
        good: { DEFAULT: "#5fb36b", dim: "#2f5a36" },
        bad: { DEFAULT: "#e0645c", dim: "#5e2b28" },
        accent: "#8fbf6a",
        warn: "#d9a441",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
