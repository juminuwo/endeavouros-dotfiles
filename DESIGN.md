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

## Agent filtering

The g action is independent of row selection and always available after loading, including empty results. Its menu offers describe/edit, reapply, search thoroughly, clear and back. Show the active prompt (or retained inactive prompt) in a dedicated line. Put new/changed-evidence warnings before the prompt so truncation cannot hide them. Match level and evidence reason appear in role details. Preserve text/family filters and tab selection, with clear empty-state guidance. A cancellable progress view shows assessed/total; replace results only after complete validation.

Quick filtering selects candidates from existing listing titles, summaries, fit notes and constraints in one request, then verifies candidates against fuller cached evidence. There is no generated-summary stage. Roles with neither meaningful summaries nor fit notes always reach detailed checking. Thorough search bypasses selection. Structured prompt parsing extracts result count/range, company uniqueness and random sampling. Apply these only after all cached/fresh assessments and thin-evidence additions. For bounded random requests, a diverse reserve pool of several times the maximum is sufficient; unconstrained selection stays broad. Sample company groups uniformly before picking a role per company. Unknown companies cannot establish distinctness. Show shortages as matches found among checked candidates and suggest thorough search; never imply quick search proved a global shortage. Cached Reapply retains the same random set. Cache by model, schema, prompt, mode and actual evidence, independently of job decisions; validated atomic cache artifacts may survive cancellation, but partial visible results must not. Explain that summaries can omit relevant details. Shortlist confirmation points to destination 2.

The board has one compact title; hide the chat context widget while browsing. Active navigation uses a solid accent fill with reverse-video text; inactive tabs have rounded outlines and normal foreground labels. Keep numeric keyboard shortcuts visible. The terminal theme remains authoritative for colors.
