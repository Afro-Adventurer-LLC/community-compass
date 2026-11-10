import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "dark";

const BASE =
  "inline-flex cursor-pointer items-center justify-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-semibold transition duration-200 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand text-white hover:opacity-90",
  secondary: "border border-border-strong bg-canvas text-ink hover:bg-surface",
  ghost: "text-muted hover:bg-surface hover:text-ink",
  dark: "bg-code text-white hover:opacity-90",
};

export function buttonClass(variant: Variant = "primary", extra = ""): string {
  return `${BASE} ${VARIANTS[variant]} ${extra}`.trim();
}

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export default function Button({
  variant = "primary",
  className = "",
  type = "button",
  ...rest
}: Props) {
  return (
    <button type={type} className={buttonClass(variant, className)} {...rest} />
  );
}

// Shared form-control styling (inputs, selects, textareas).
export const inputClass =
  "w-full rounded-lg border border-border-strong bg-canvas px-3 py-2 text-sm text-ink placeholder:text-muted transition duration-200 focus:border-brand-purple";

// Frosted variant for inputs that sit on glass surfaces.
export const glassInputClass =
  "glass-input w-full rounded-lg border border-[var(--glass-border)] bg-canvas/50 px-3 py-2 text-sm text-ink placeholder:text-muted shadow-[0_0_0_1px_var(--glass-ring)] backdrop-blur-md transition duration-200 focus:border-brand-purple focus:bg-canvas/80";
