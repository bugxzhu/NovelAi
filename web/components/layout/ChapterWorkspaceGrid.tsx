"use client";

import { type ReactNode } from "react";
import { useUIStore } from "@/lib/store";

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
            style={{ width: contextPanelWidth }}
            className="shrink-0 border-l border-line overflow-hidden bg-panel"
          >
            {contextPanel}
          </aside>
        )}
      </div>
      {bottomPanel && (
        <div
          style={{ height: bottomPanelOpen ? bottomPanelHeight : 28 }}
          className="shrink-0 border-t border-line bg-panel overflow-hidden transition-[height] duration-150"
        >
          {bottomPanel}
        </div>
      )}
    </div>
  );
}
