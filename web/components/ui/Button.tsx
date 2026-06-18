import { type ButtonHTMLAttributes, forwardRef } from "react";

type Variant = "primary" | "ghost" | "danger" | "subtle";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

const STYLES: Record<Variant, string> = {
  primary: "bg-[#0e639c] hover:bg-[#1177bb] text-white",
  ghost: "bg-transparent hover:bg-[#3a3a3a] text-[#cccccc]",
  danger: "bg-red-900 hover:bg-red-800 text-red-100",
  subtle: "bg-[#3c3c3c] hover:bg-[#4c4c4c] text-[#cccccc]",
};

export const Button = forwardRef<HTMLButtonElement, Props>(
  ({ variant = "subtle", className = "", ...rest }, ref) => (
    <button
      ref={ref}
      className={`px-3 py-1.5 rounded text-sm disabled:opacity-40 disabled:cursor-not-allowed ${STYLES[variant]} ${className}`}
      {...rest}
    />
  )
);
Button.displayName = "Button";
