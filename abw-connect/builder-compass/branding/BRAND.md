# Builder Compass — Design System & Brand Guidelines

## Product identity

Builder Compass is a premium, developer-focused conference discovery and planning platform, initially for **AWS re:Invent 2026**. It helps developers, cloud architects, engineers, founders, and tech professionals discover sessions, plan schedules, navigate venues, and find networking opportunities.

> Independent, unofficial planner. Not affiliated with or endorsed by AWS.

## Design philosophy

Polished, friendly, minimalist — inspired by **Apple, Linear, Raycast, and Vercel**. The interface must feel:

- Premium but approachable
- Minimal but functional
- Professional but not corporate-heavy
- Modern but not visually experimental
- Consistent across every screen

Never ship generic, AI-generated-looking dashboards.

## Logo

- **Mark:** a navigation arrow / paper-plane in a soft light squircle (34px radius tile), brand gradient fill, with a warm glow pooling at the tail. The folded underside catches the orange.
- **Wordmark:** "Builder" (Inter 700, `#171923`) + "Compass" (Inter 500, `#777B89`).
- **Monochrome fallback:** white arrow on `#171923` squircle for dense/dark contexts.
- Files: `branding/logo.svg`, `branding/brand-board.svg`, with PNG exports alongside.

## Brand colours

| Token | Hex | Role |
|---|---|---|
| Primary text | `#171923` | headings, body |
| Background | `#FFFFFF` | app background |
| Secondary background | `#F6F7FA` | panels, fills, app shell |
| Muted text | `#777B89` | secondary text, meta |
| Primary purple | `#6446F5` | brand, primary emphasis |
| Secondary blue | `#4388F5` | brand, links |
| Accent orange | `#FF9A43` | highlights, gradient tail |
| Success | `#16A36A` | success / reachable |
| Warning | `#D97706` | warning / tight |
| Error | `#DC5555` | error / not reachable |

**Brand gradient:** `#6446F5 → #4388F5 → #FF9A43`. Use **sparingly** — selected states, branding, primary CTA, highlights. Not decoration.

## Typography

- **Inter** (or **Geist Sans**) throughout the UI. Base 16px, line-height ~1.6, clear hierarchy, generous whitespace.
- **Geist Mono** for technical identifiers: session codes, times, walk minutes, venue strings.

## Component guidelines

- Corner radius **12–16px**, consistent.
- Subtle borders (`#EDEEF3` / `#E2E4EC`), minimal shadows (one soft elevation, not on everything).
- **Lucide** icons, consistent sizing and stroke. Never emoji as icons.
- Restrained buttons: primary = brand gradient; secondary = white + border; selected = `#F0ECFE` / `#6446F5` text.
- Every interactive element has clear hover / focus / active / disabled / loading states.
- Transitions **150–250ms**.
- Centralized spacing + colour tokens (see `tailwind.config.ts`; `app/globals.css` reads from it).
- Accessible contrast (≥ 4.5:1), visible keyboard focus.

### Signature component — feasibility pill
Dot + label + minutes, tinted by state: success (reachable), warning (tight), error (not reachable). Reused on cards, session detail, and every stack block. The green/amber/red here is **semantic only**.

## UX guidelines

- Prioritise clarity and usability; make important actions immediately discoverable.
- Keep navigation simple (persistent sidebar on desktop, bottom/collapsed on mobile).
- Avoid unnecessary modals; prefer inline panels and drawers.
- Support desktop, tablet, mobile. Verify at 375 / 768 / 1024 / 1440.
- Design useful empty, loading, and error states (direction, not mood).
- Preserve user selections and filters across navigation.
- Make session discovery and agenda planning effortless.

## Strict restrictions — avoid

Excessive gradients · excessive glassmorphism · unnecessary decorative elements · generic AI illustrations · random colour choices · inconsistent components · excessive rounded containers · unnecessary animations · dense dashboard layouts.

## Development rules

1. Reuse existing design-system components.
2. Don't duplicate UI patterns unnecessarily.
3. Centralise all design tokens in the Tailwind theme (`tailwind.config.ts`).
4. Keep components modular and maintainable.
5. Use realistic product content — never lorem ipsum.
6. Verify responsiveness at mobile / tablet / desktop.
7. Maintain accessibility and keyboard navigation.
8. Before building a new page, inspect existing components and follow the established language.

Every new feature must look and behave as if it belongs to the same product.
