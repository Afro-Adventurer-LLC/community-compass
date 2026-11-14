"use client";

import { useEffect, useRef } from "react";

// The brand mark as a living compass: the needle turns to point at the cursor
// (or finger), and the tile zooms slightly on hover and presses in on click.
// Purely decorative, so it is hidden from assistive tech, and it stays still
// when the user prefers reduced motion.
export default function CompassMark({ size = 96 }: { size?: number }) {
  const tileRef = useRef<HTMLDivElement>(null);
  const needleRef = useRef<SVGGElement>(null);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (reduce.matches) return;

    let frame = 0;
    const aim = (e: PointerEvent) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const tile = tileRef.current;
        const needle = needleRef.current;
        if (!tile || !needle) return;
        const r = tile.getBoundingClientRect();
        const dx = e.clientX - (r.left + r.width / 2);
        const dy = e.clientY - (r.top + r.height / 2);
        // The artwork points up-right (-45deg), so offset by +45.
        const deg = (Math.atan2(dy, dx) * 180) / Math.PI + 45;
        needle.style.transform = `rotate(${deg}deg)`;
      });
    };

    window.addEventListener("pointermove", aim);
    return () => {
      window.removeEventListener("pointermove", aim);
      cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <div
      ref={tileRef}
      aria-hidden
      style={{ width: size, height: size }}
      className="shrink-0 cursor-pointer select-none rounded-[28%] shadow-card transition-transform duration-200 ease-out hover:scale-110 active:scale-95"
    >
      <svg viewBox="0 0 512 512" width="100%" height="100%" className="block">
        <defs>
          <linearGradient id="cm-a" x1="0.1" y1="0.05" x2="0.7" y2="1">
            <stop offset="0" stopColor="#6446F5" />
            <stop offset="0.45" stopColor="#4388F5" />
            <stop offset="0.82" stopColor="#FF9A43" />
            <stop offset="1" stopColor="#FF7A2F" />
          </linearGradient>
          <linearGradient id="cm-f" x1="0.3" y1="0" x2="0.5" y2="1">
            <stop offset="0" stopColor="#5B3EF0" />
            <stop offset="1" stopColor="#FF8A3A" />
          </linearGradient>
          <linearGradient id="cm-t" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#FBFBFE" />
            <stop offset="1" stopColor="#EEF0F7" />
          </linearGradient>
          <radialGradient id="cm-g" cx="50%" cy="80%" r="55%">
            <stop offset="0" stopColor="#FF9A43" stopOpacity="0.5" />
            <stop offset="0.6" stopColor="#6446F5" stopOpacity="0.16" />
            <stop offset="1" stopColor="#6446F5" stopOpacity="0" />
          </radialGradient>
        </defs>
        <rect width="512" height="512" rx="144" fill="url(#cm-t)" />
        <rect x="30" y="30" width="452" height="452" rx="120" fill="url(#cm-g)" />
        <g transform="translate(256,256)">
          <g
            ref={needleRef}
            style={{
              transition: "transform 250ms ease-out",
              transformBox: "view-box",
              transformOrigin: "0 0",
            }}
          >
            <g transform="scale(3.4)">
              <path d="M 25 -25 L -22 -2 L -2 7 L 7 27 Z" fill="url(#cm-a)" />
              <path d="M -2 7 L 7 27 L 9 2 Z" fill="url(#cm-f)" />
            </g>
          </g>
        </g>
      </svg>
    </div>
  );
}
