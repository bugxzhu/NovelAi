import { type ReactNode } from "react";

export function Chip({
  children,
  selected,
  onClick,
  className = "",
}: {
  children: ReactNode;
  selected?: boolean;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-2 py-0.5 rounded text-xs border ${
        selected
          ? "bg-[#0e639c] border-[#1177bb] text-white"
          : "bg-[#3c3c3c] border-[#4c4c4c] text-[#cccccc] hover:bg-[#4c4c4c]"
      } ${className}`}
    >
      {children}
    </button>
  );
}
