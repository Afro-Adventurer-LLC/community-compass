import type { Config } from "tailwindcss";

// ---------------------------------------------------------------------------
// Builder Compass design tokens — single source of truth for the UI.
// Premium, minimal, developer-focused (Apple / Linear / Raycast / Vercel).
// app/globals.css reads these with theme().
// ---------------------------------------------------------------------------

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Neutrals
        ink: "rgb(var(--c-ink) / <alpha-value>)", // primary text
        muted: "rgb(var(--c-muted) / <alpha-value>)", // muted text
        canvas: "rgb(var(--c-canvas) / <alpha-value>)", // cards, sidebar
        surface: "rgb(var(--c-surface) / <alpha-value>)", // app shell
        code: "rgb(var(--c-code) / <alpha-value>)", // always-dark code blocks
        border: "rgb(var(--c-border) / <alpha-value>)",
        "border-strong": "rgb(var(--c-border-strong) / <alpha-value>)",

        // Brand
        brand: {
          purple: "rgb(var(--c-brand-purple) / <alpha-value>)",
          blue: "rgb(var(--c-brand-blue) / <alpha-value>)",
          orange: "rgb(var(--c-brand-orange) / <alpha-value>)",
          tint: "rgb(var(--c-brand-tint) / <alpha-value>)", // selected-state fill
        },

        // Semantic (status + walk-feasibility)
        success: "rgb(var(--c-success) / <alpha-value>)",
        warning: "rgb(var(--c-warning) / <alpha-value>)",
        error: "rgb(var(--c-error) / <alpha-value>)",

        // Darker status text for AA contrast on tinted status backgrounds
        "success-fg": "rgb(var(--c-success-fg) / <alpha-value>)",
        "warning-fg": "rgb(var(--c-warning-fg) / <alpha-value>)",
        "error-fg": "rgb(var(--c-error-fg) / <alpha-value>)",
      },
      fontFamily: {
        // --font-sans / --font-mono come from next/font in app/layout.tsx
        sans: [
          "var(--font-sans)",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "var(--font-mono)",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
      borderRadius: {
        lg: "12px",
        xl: "14px",
        "2xl": "16px",
      },
      boxShadow: {
        // one restrained elevation — not on everything
        card: "var(--shadow-card)",
      },
      backgroundImage: {
        // brand gradient — use sparingly (CTA, selected, branding)
        brand: "var(--brand-gradient)",
      },
      transitionDuration: {
        DEFAULT: "200ms",
      },
    },
  },
  plugins: [],
};

export default config;
