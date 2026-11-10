// Toggle chip used for filters and profile choices.
export default function Chip({
  active,
  onClick,
  children,
  glass = false,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  glass?: boolean;
}) {
  const idle = glass
    ? "glass-pill text-ink"
    : "border-border-strong bg-canvas text-ink hover:bg-surface";
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`min-h-[36px] cursor-pointer rounded-lg border px-3 py-1.5 text-sm transition duration-200 ${
        active
          ? "border-brand-purple/30 bg-brand-tint font-semibold text-brand-purple"
          : idle
      }`}
    >
      {children}
    </button>
  );
}
