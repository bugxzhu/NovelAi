"use client";

import { type ReactNode } from "react";
import { ActivityBar } from "./ActivityBar";

export function WorkspaceShell({
  projectId,
  children,
}: {
  projectId: number;
  children: ReactNode;
}) {
  return (
    <div className="flex h-screen overflow-hidden">
      <ActivityBar projectId={projectId} />
      <div className="flex-1 flex flex-col overflow-hidden">{children}</div>
    </div>
  );
}
