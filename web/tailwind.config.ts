import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        serif: ['"Source Han Serif SC"', '"Noto Serif SC"', "Georgia", "serif"],
      },
      colors: {
        bg: { DEFAULT: "#1e1e1e", panel: "#252526", sidebar: "#333" },
        border: { DEFAULT: "#3c3c3c" },
        accent: { DEFAULT: "#0e639c", hover: "#1177bb" },
        text: { DEFAULT: "#cccccc", muted: "#888888" },
      },
    },
  },
  plugins: [],
};

export default config;
