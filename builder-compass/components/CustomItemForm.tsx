"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { useCompassStore } from "@/lib/store";
import { venueGraphSync } from "@/lib/data";
import { toVegasIso } from "@/lib/format";
import Button, { inputClass } from "@/components/ui/Button";

function Field({
  label,
  className = "",
  children,
}: {
  label: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label className={`block text-sm ${className}`}>
      <span className="mb-1.5 block font-medium text-ink">{label}</span>
      {children}
    </label>
  );
}

export default function CustomItemForm() {
  const addCustomItem = useCompassStore((s) => s.addCustomItem);
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [venue, setVenue] = useState("");
  const [room, setRoom] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [error, setError] = useState<string | null>(null);

  const venues = venueGraphSync().venues;

  function submit() {
    setError(null);
    if (!title.trim() || !start || !end) {
      setError("Add a title, start time, and end time.");
      return;
    }
    if (new Date(end).getTime() <= new Date(start).getTime()) {
      setError("End time must be after the start time.");
      return;
    }
    addCustomItem({
      title: title.trim(),
      venue: venue || undefined,
      room: room || undefined,
      start: toVegasIso(start),
      end: toVegasIso(end),
    });
    setTitle("");
    setVenue("");
    setRoom("");
    setStart("");
    setEnd("");
    setOpen(false);
  }

  if (!open) {
    return (
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <Plus size={16} strokeWidth={2} aria-hidden />
        Add a custom block
      </Button>
    );
  }

  return (
    <div className="rounded-2xl border border-border bg-canvas p-5 shadow-card">
      <h3 className="mb-1 font-semibold text-ink">Add a custom block</h3>
      <p className="mb-4 text-sm text-muted">
        Parties, meals, and 1:1s. Times are Las Vegas time. Add a venue to get
        walk checks against the blocks around it.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Title" className="sm:col-span-2">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Dinner with the platform team"
            className={inputClass}
          />
        </Field>
        <Field label="Venue (optional)">
          <select
            value={venue}
            onChange={(e) => setVenue(e.target.value)}
            className={inputClass}
          >
            <option value="">No venue</option>
            {venues.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Room (optional)">
          <input
            value={room}
            onChange={(e) => setRoom(e.target.value)}
            className={inputClass}
          />
        </Field>
        <Field label="Start">
          <input
            type="datetime-local"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className={inputClass}
          />
        </Field>
        <Field label="End">
          <input
            type="datetime-local"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className={inputClass}
          />
        </Field>
      </div>
      {error && (
        <p role="alert" className="mt-3 text-sm text-error-fg">
          {error}
        </p>
      )}
      <div className="mt-4 flex gap-2">
        <Button onClick={submit}>Add block</Button>
        <Button variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
