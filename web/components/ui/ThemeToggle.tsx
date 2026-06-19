"use client";

import { useUIStore } from "@/lib/store";

export function ThemeToggle() {
  const theme = useUIStore((s) => s.theme);
  const toggleTheme = useUIStore((s) => s.toggleTheme);
  return (
    <button
      onClick={toggleTheme}
      title={theme === "dark" ? "切换到亮色" : "切换到暗色"}
      className="w-8 h-8 flex items-center justify-center rounded text-base hover:bg-hover-strong text-text-muted hover:text-text"
    >
      {theme === "dark" ? "☀️" : "🌙"}
    </button>
  );
}
