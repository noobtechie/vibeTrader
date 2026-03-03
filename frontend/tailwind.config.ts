import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Trading-specific colors
        profit: {
          DEFAULT: "#22c55e",
          light: "#dcfce7",
          dark: "#15803d",
        },
        loss: {
          DEFAULT: "#ef4444",
          light: "#fee2e2",
          dark: "#b91c1c",
        },
        neutral: {
          DEFAULT: "#94a3b8",
        },
        // Background
        surface: {
          DEFAULT: "#0f172a",
          card: "#1e293b",
          elevated: "#334155",
          border: "#475569",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
