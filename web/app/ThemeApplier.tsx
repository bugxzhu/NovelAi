"use client";

import { useEffect } from "react";
import { useUIStore } from "@/lib/store";

// Syncs the persisted theme in the store to the `dark` class on <html>.
export function ThemeApplier() {
  const theme = useUIStore((s) => s.theme);
  useEffect(() => {
    if (theme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, [theme]);
  return null;
}
