"use client";

import { type ReactNode } from "react";

export function SidePanel({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-3 py-2 border-b border-line">
        <span className="text-xs uppercase text-text-muted font-semibold">{title}</span>
        {action}
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">{children}</div>
    </div>
  );
}
