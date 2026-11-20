import type { HTMLAttributes } from "react";

// The one card surface used across the app: subtle border, one soft elevation.
// `glass` swaps in the frosted surface (needs `.glass-ambient` behind it).
export default function Card({
  className = "",
  glass = false,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { glass?: boolean }) {
  return (
    <div
      className={`rounded-2xl p-5 ${
        glass ? "glass" : "border border-border bg-canvas shadow-card"
      } ${className}`}
      {...rest}
    />
  );
}
