"use client";

import { type ReactNode, useCallback, useEffect, useRef } from "react";
import { useUIStore } from "@/lib/store";

const MIN_HEIGHT = 100;
const MAX_HEIGHT_RATIO = 0.85; // max 85% of viewport

export function ChapterWorkspaceGrid({
  sidePanel,
  editor,
  contextPanel,
  bottomPanel,
}: {
  sidePanel: ReactNode;
  editor: ReactNode;
  contextPanel?: ReactNode;
  bottomPanel?: ReactNode;
}) {
  const sidePanelWidth = useUIStore((s) => s.sidePanelWidth);
  const contextPanelWidth = useUIStore((s) => s.contextPanelWidth);
  const bottomPanelOpen = useUIStore((s) => s.bottomPanelOpen);
  const bottomPanelHeight = useUIStore((s) => s.bottomPanelHeight);
  const setBottomPanelHeight = useUIStore((s) => s.setBottomPanelHeight);
  const contextPanelOpen = useUIStore((s) => s.contextPanelOpen);
  const toggleContextPanel = useUIStore((s) => s.toggleContextPanel);

  const dragRef = useRef<{ startY: number; startHeight: number } | null>(null);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (!bottomPanelOpen) return;
      e.preventDefault();
      dragRef.current = { startY: e.clientY, startHeight: bottomPanelHeight };

      const onMove = (ev: MouseEvent) => {
        if (!dragRef.current) return;
        const delta = dragRef.current.startY - ev.clientY;
        const next = dragRef.current.startHeight + delta;
        const maxH = window.innerHeight * MAX_HEIGHT_RATIO;
        setBottomPanelHeight(Math.max(MIN_HEIGHT, Math.min(maxH, next)));
      };

      const onUp = () => {
        dragRef.current = null;
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      };

      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
      document.body.style.cursor = "ns-resize";
      document.body.style.userSelect = "none";
    },
    [bottomPanelOpen, bottomPanelHeight, setBottomPanelHeight]
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, []);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex-1 flex overflow-hidden">
        <aside
          style={{ width: sidePanelWidth }}
          className="shrink-0 border-r border-line overflow-hidden bg-panel"
        >
          {sidePanel}
        </aside>
        <main className="flex-1 min-w-[500px] overflow-hidden bg-input">
          {editor}
        </main>
        {contextPanel && (
          <aside
            style={{ width: contextPanelOpen ? contextPanelWidth : 10 }}
            className="relative shrink-0 border-l border-line bg-panel overflow-hidden transition-[width] duration-150"
          >
            <button
              type="button"
              onClick={toggleContextPanel}
              title={contextPanelOpen ? "折叠右栏" : "展开右栏"}
              aria-label={contextPanelOpen ? "折叠右栏" : "展开右栏"}
              aria-expanded={contextPanelOpen}
              className="absolute left-0 top-0 h-full w-[10px] flex items-center justify-center text-xs text-text-muted hover:bg-hover hover:text-text cursor-pointer"
            >
              {contextPanelOpen ? "◂" : "▸"}
            </button>
            {contextPanelOpen && (
              <div className="h-full pl-[10px] overflow-hidden">{contextPanel}</div>
            )}
          </aside>
        )}
      </div>

      {/* Drag handle — only visible when bottom panel is open */}
      {bottomPanel && bottomPanelOpen && (
        <div
          onMouseDown={onMouseDown}
          className="shrink-0 h-1.5 bg-line hover:bg-accent cursor-ns-resize transition-colors"
          title="上下拖动调整面板高度"
        />
      )}

      {bottomPanel && (
        <div
          style={{ height: bottomPanelOpen ? bottomPanelHeight : 28 }}
          className="shrink-0 border-t border-line bg-panel overflow-hidden"
        >
          {bottomPanel}
        </div>
      )}
    </div>
  );
}
