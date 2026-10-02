# Design

## Foundations
- Colour: OKLCH, tinted neutrals toward hue 275, one accent (`--accent`), semantic tones good/warn/bad each with a wash. Contrast asserted in `frontend/src/test/tokens.test.ts`.
- Type: Figtree (400/500/600/700) with system fallback; mono for codes and quotes; tabular numerals for all money.
- Space: 4px base scale `--s1`..`--s8`. Radius 10px containers, 6px controls.
- Depth: borders for panels; one shadow (`--shadow`) reserved for the paper preview.
- Motion: 150-240ms exponential ease-out, state changes only, reduced-motion respected.

## Layout
Sidebar (14.5rem) + content (max 80rem). Below 900px the sidebar becomes a top strip. Tables scroll inside focusable `.table-scroll` regions.

## Components
Pill (status, dot + text), Tabs (WAI-ARIA tablist), Switch, EmptyState, Skeleton, PageHeader, DataTable (`.data`), SummaryStrip, StatusBar, ActivityChart, Paper (document preview), AgentTimeline.

## Bans
No glass, no gradients, no side-stripe borders, no nested cards, no gradient text, no identical stat-card grids. Enforced by `frontend/src/test/styles.test.ts`.
