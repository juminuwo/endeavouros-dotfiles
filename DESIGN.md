---
name: Career Terminal Workspace
version: 1
scope: config/career
---

# Career Terminal Workspace

This dotfiles repository owns a small Pi extension for Adrian's job search. Other desktop configuration keeps its existing appearance.

## Visual direction

A keyboard-first role browser, recognisable as a terminal application. Immediate access to real jobs, clear selection, and quiet metadata. Personality comes from approachable wording and responsive interaction; no points, streaks or decorative animation.

Use the active Pi theme's semantic tokens and the user's terminal font. Reference dark palette: canvas #191724, surface #26233a, text #e0def4, muted #908caa, accent #9ccfd8, warning #f6c177. These describe roles; do not hardcode them over a user's Pi theme. Errors use the theme error color. A selected row uses selectedBg plus an accent marker and bold text so color alone never carries selection.

## Layout and components

Header, four destination tabs, filter, list/detail area, operation feedback, then persistent key help. At 105 columns and above, split the content approximately 46/54. Below that, show the list and offer v for full-width detail. Expanded detail scrolls independently. Clip/wrap using Pi's visible-column helpers, including wide Unicode. Bound height to the current terminal; do not let a long vacancy overflow the input controls.

Selection and filters survive discussion and return. Tab/1–4 switches destination; arrows and j/k navigate; Enter opens the discoverable action menu; slash filters; question mark shows help; Escape returns one level or to agent chat. Ctrl+Alt+C opens the board from chat. Menus and inputs use Pi components.

## Feedback

Browsing is immediate and local. Save operations disable repeated actions while in flight. Success is shown only after durable confirmation. Conflicts tell the user to reload; projection warnings distinguish a saved choice from a stale Markdown view. Display listing age and lifecycle, and label old automated scores as legacy ML scores rather than a new DS ranking. Inactive saved roles stay visible. Empty states suggest changing filters or returning to Discover.
