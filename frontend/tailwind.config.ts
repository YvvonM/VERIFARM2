import type { Config } from "tailwindcss";

// Theme tokens mirror the CSS variables in globals.css (ported from chris-frontend).
const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        card: "var(--card)",
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)",
        },
        secondary: "var(--secondary)",
        accent: "var(--accent)",
        destructive: "var(--destructive)",
        "muted-foreground": "var(--muted-foreground)",
        border: "var(--border)",
        input: "var(--input)",
        ring: "var(--ring)",
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
        display: ["Anton", "sans-serif"],
        accent: ["Caveat", "cursive"],
        mono: ["JetBrains Mono", "monospace"],
      },
      borderRadius: {
        xl: "1rem",
        "2xl": "1.25rem",
      },
    },
  },
  plugins: [],
};

export default config;
