"use client";

import { useState } from "react";
import { SettingsModal } from "@/components/layout/SettingsModal";

/**
 * A small ⚙️ button that opens the global (read-only) LLM settings modal.
 * Drop it anywhere settings access is wanted (ActivityBar, home page top bar, ...).
 */
export function SettingsButton({ className = "" }: { className?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        title="AI 设置"
        className={
          "w-8 h-8 flex items-center justify-center rounded text-base hover:bg-hover-strong text-text-muted hover:text-text " +
          className
        }
      >
        <span className="leading-none">⚙️</span>
      </button>
      <SettingsModal open={open} onClose={() => setOpen(false)} />
    </>
  );
}
