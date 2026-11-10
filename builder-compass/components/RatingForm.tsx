"use client";

import { Star } from "lucide-react";
import type { SessionRating } from "@/types";
import { useCompassStore } from "@/lib/store";
import Chip from "@/components/ui/Chip";
import { inputClass } from "@/components/ui/Button";

// The four-field evaluation: rating, would you recommend it, one takeaway,
// and action items. Saves as you type.
export default function RatingForm({
  sessionId,
  title,
  rating,
}: {
  sessionId: string;
  title: string;
  rating?: SessionRating;
}) {
  const patchRating = useCompassStore((s) => s.patchRating);
  const value = rating?.value ?? 0;
  const recommend = rating?.wouldRecommend;

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div>
        <div className="mb-1.5 text-sm font-medium text-ink" id={`rate-${sessionId}`}>
          How useful was it?
        </div>
        <div role="group" aria-labelledby={`rate-${sessionId}`} className="flex gap-1">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              aria-label={`${n} star${n === 1 ? "" : "s"} for ${title}`}
              aria-pressed={value === n}
              // Choosing the current rating again clears it.
              onClick={() => patchRating(sessionId, { value: value === n ? 0 : n })}
              className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-lg transition duration-200 hover:bg-surface"
            >
              <Star
                size={22}
                strokeWidth={1.5}
                className={
                  n <= value ? "fill-brand-orange text-brand-orange" : "text-border-strong"
                }
                aria-hidden
              />
            </button>
          ))}
        </div>
      </div>

      <div>
        <div className="mb-1.5 text-sm font-medium text-ink">Would you recommend it?</div>
        <div className="flex gap-2">
          <Chip
            active={recommend === true}
            onClick={() =>
              patchRating(sessionId, { wouldRecommend: recommend === true ? undefined : true })
            }
          >
            Yes
          </Chip>
          <Chip
            active={recommend === false}
            onClick={() =>
              patchRating(sessionId, { wouldRecommend: recommend === false ? undefined : false })
            }
          >
            No
          </Chip>
        </div>
      </div>

      <label className="block text-sm sm:col-span-2">
        <span className="mb-1.5 block font-medium text-ink">Biggest takeaway</span>
        <input
          value={rating?.takeaway ?? ""}
          onChange={(e) => patchRating(sessionId, { takeaway: e.target.value })}
          placeholder="The one thing you would tell your team"
          className={inputClass}
        />
      </label>

      <label className="block text-sm sm:col-span-2">
        <span className="mb-1.5 block font-medium text-ink">Action items</span>
        <textarea
          rows={2}
          value={rating?.actionItems ?? ""}
          onChange={(e) => patchRating(sessionId, { actionItems: e.target.value })}
          placeholder="What will you try, share, or follow up on?"
          className={inputClass}
        />
      </label>
    </div>
  );
}
