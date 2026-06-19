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
          ? "bg-accent border-accent-hover text-white"
          : "bg-button border-line text-text hover:bg-button-hover"
      } ${className}`}
    >
      {children}
    </button>
  );
}
