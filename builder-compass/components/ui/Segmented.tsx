// A compact single-choice control (day tabs, Schedule/Report switch, ...).
interface Option<T extends string> {
  value: T;
  label: string;
}

export default function Segmented<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
  glass = false,
}: {
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
  glass?: boolean;
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={`flex max-w-full gap-1 overflow-x-auto rounded-xl p-1 ${
        glass ? "glass" : "bg-canvas ring-1 ring-border"
      }`}
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(o.value)}
            className={`min-h-[36px] shrink-0 cursor-pointer rounded-lg px-3 text-sm font-medium transition duration-200 ${
              active
                ? glass
                  ? "bg-canvas/90 text-brand-purple shadow-card"
                  : "bg-brand-tint text-brand-purple"
                : glass
                  ? "text-muted hover:bg-canvas/40 hover:text-ink"
                  : "text-muted hover:bg-surface hover:text-ink"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
