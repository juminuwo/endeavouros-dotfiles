---
name: research-first
description: Resolve consequential unanswered domain or technical assumptions before implementation. Use for unfamiliar business rules, external API contracts, data formats, or architecture decisions; reuse approved repository decisions and supplied research instead of reopening settled choices.
---

# Research before implementation

Start with the requested outcome, repository decisions, existing contracts, and
supplied research. Separate settled behavior, routine implementation choices,
and genuinely unresolved assumptions. Do not research every coding choice or
require renewed approval for an approach already authorized. Mechanical edits
and established repository patterns need no research ceremony.

## Resolve the unknown

For each consequential assumption, name the question and what would change if
it is wrong. Read the relevant primary source: official API or dependency docs,
an applicable standard, or authoritative domain guidance. Use enough evidence
to resolve the question; there is no minimum source count. Seek additional
sources when evidence conflicts or the consequence warrants it.

For behavior of installed code or dependencies, prefer a focused executable
probe over inference from documentation alone. Distinguish a documented fact,
an observation, and a recommendation. An industry convention does not decide
this product's undocumented business policy.

## Decide at the right level

Present a short brief only for material unresolved choices: outcome, evidence,
recommendation, and meaningful tradeoff. Ask for an owner decision when it
changes product policy, scope, contracts, security, privacy, operational cost,
or a hard-to-reverse architecture choice. Wait on the affected path while
continuing independent authorized work.

Existing approval remains valid unless new evidence changes its consequence.
Do not ask the user to choose names, helpers, test structure, or equivalent
implementation details. Choose the simplest reversible option that meets the
approved contract. Record material decisions in the repository's owning
document and proceed. Keep rationale comments only where they explain a
non-obvious constraint; do not narrate research in source code.
