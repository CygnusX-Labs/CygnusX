---
name: omichub-frontend-design
description: Apply the OmicHub scientific-workbench frontend design system to Vue 3 applications. Use when implementing or reviewing OmicHub pages, layouts, dashboards, forms, data tables, loading/error/empty states, responsive behavior, accessibility, themes, motion, or when migrating the system to another Vue platform using either Naive UI or Arco Design Vue.
---

# OmicHub Frontend Design

Apply a calm, reliable scientific-workbench design system. Keep the implementation consistent with the application's existing component library; never mix Naive UI and Arco Design Vue in one application.

## Workflow

1. Read `references/frontend-design-system.md` completely before editing UI code.
2. Inspect the target repository's `AGENTS.md`, existing theme setup, global CSS variables, page shell, and shared components.
3. Identify the existing component library. Use Naive UI in OmicHub; use Arco only when the target application already chose and configured Arco.
4. Reuse semantic tokens, the shared page header, and existing page patterns before adding component-local styles.
5. Implement the full interaction model: default, hover, active, focus-visible, disabled, loading, empty, error, and success as applicable.
6. Keep page refreshes local and state-preserving. Never use route or browser reload as a data-refresh mechanism.
7. Verify light/dark themes, narrow screens, keyboard access, reduced motion, reduced transparency, and high contrast.
8. Run the project's targeted type check, build, and any relevant tests. Update the design-system reference when adding a global token or reusable pattern.

## Decision Rules

- Use CSS semantic variables instead of hard-coded page colors, borders, shadows, or chart rails.
- Put page-level actions in the shared header; keep card actions scoped to the card they affect.
- Present operational status with text plus color and loading/error semantics; decorative status dots must not be the sole signal.
- For selectable cards, use the shared `.omichub-selectable-card` contract with `.is-selected` and the matching ARIA state; preserve both the continuous selected outline and left status rail.
- Reserve glass materials for structural chrome and authentication contexts. Use solid cards for normal content.
- Use short transitions for ordinary UI state. Use interruptible springs only for direct gesture interactions.
- Keep the skill reference as the canonical cross-platform specification. Follow repository-local instructions when they conflict.

## Reference

Load `references/frontend-design-system.md` for token definitions, component contracts, dashboard state patterns, responsive breakpoints, accessibility requirements, component-library migration guidance, and the delivery checklist.
