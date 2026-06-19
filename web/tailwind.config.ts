import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
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
        input: "var(--color-input)",
        panel: "var(--color-panel)",
        sidebar: "var(--color-sidebar)",
        active: "var(--color-active)",
        line: "var(--color-line)",
        hover: "var(--color-hover)",
        "hover-strong": "var(--color-hover-strong)",
        button: {
          DEFAULT: "var(--color-button)",
          hover: "var(--color-button-hover)",
        },
        accent: {
          DEFAULT: "var(--color-accent)",
          strong: "var(--color-accent-strong)",
          hover: "var(--color-accent-hover)",
        },
        text: {
          DEFAULT: "var(--color-text)",
          muted: "var(--color-text-muted)",
          "muted-bright": "var(--color-text-muted-bright)",
          dim: "var(--color-text-dim)",
        },
      },
      textColor: {
        input: "var(--color-input)",
        panel: "var(--color-panel)",
        sidebar: "var(--color-sidebar)",
        active: "var(--color-active)",
        line: "var(--color-line)",
        hover: "var(--color-hover)",
        "hover-strong": "var(--color-hover-strong)",
        button: "var(--color-button)",
        "button-hover": "var(--color-button-hover)",
        accent: "var(--color-accent)",
        "accent-strong": "var(--color-accent-strong)",
        "accent-hover": "var(--color-accent-hover)",
      },
      borderColor: {
        line: "var(--color-line)",
        accent: "var(--color-accent)",
        "accent-hover": "var(--color-accent-hover)",
      },
    },
  },
  plugins: [],
};

export default config;
