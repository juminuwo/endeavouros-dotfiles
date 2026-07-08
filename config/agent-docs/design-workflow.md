# DESIGN.md Workflow

Version: 1
Status: Active shared convention

`DESIGN.md` is the repo-local, agent-facing source for a product's visual
identity and design-system tokens. It is for UI implementation guidance, not a
replacement for product requirements, architecture decisions, research notes, or
project runbooks.

## When To Read It

For frontend or UI work:

1. Read the repo `AGENTS.md`.
2. Read the repo root `DESIGN.md` when it exists.
3. Read any detailed UI guidance linked from `DESIGN.md` or the repo
   `AGENTS.md`.
4. Then inspect the implementation files that define the actual styling system.

Treat YAML front matter in `DESIGN.md` as the exact token layer and the Markdown
body as the rationale for using those tokens. When the implementation and
`DESIGN.md` disagree, inspect the code and update the stale document or ask for
direction before making broad visual changes.

## When To Create One

Create a root `DESIGN.md` for a UI repo when:

- The repo has recurring frontend work and no compact design-system entrypoint.
- You are making visual decisions that future agents need to preserve.
- Styling tokens or component vocabulary already exist in code but are not
  documented in one place.

Start from `~/git/docs/templates/DESIGN.md`. Keep the first version small and
truthful. Record the current system before proposing a redesign.

Do not create `DESIGN.md` for non-UI repos unless the user asks or the repo has
UI assets whose visual identity needs agent-readable guidance.

## How To Maintain It

Update `DESIGN.md` in the same change when UI work changes:

- Core colors, typography, spacing, radii, elevation, or component tokens.
- Shared component vocabulary or display-density rules.
- Semantic color usage, accessibility constraints, or touch-target standards.
- Links to detailed design research or UI runbooks.

Keep project-specific UX decisions in the project repo. Shared dotfiles docs
define this process and starter template only; they do not define a global
Imoto Labs visual brand.

## Relationship To Repo Docs

Use this split:

- `DESIGN.md`: visual identity, tokens, component guidance, and UI do/don'ts.
- Product docs: workflow scope, user needs, acceptance criteria.
- Architecture docs: data model, security, deployment, integration decisions.
- Research docs: evidence, alternatives considered, open questions.
- Runbooks: operational procedures.

When a detailed project UI standard exists, link it from `DESIGN.md` rather than
duplicating the whole document.

## Linting

Validate structure with the Google `DESIGN.md` CLI:

```sh
npx -y @google/design.md lint DESIGN.md
```

The linter checks YAML structure, token references, section order, component
sub-token names, and contrast signals. Warnings are useful review input; errors
must be fixed before treating the file as the design-system source.

If the npm registry or CLI is unavailable, run these fallback checks:

```sh
sed -n '1,220p' DESIGN.md
git diff --check -- DESIGN.md
```

For project-specific verification, also run that repo's normal Markdown or doc
checks when they exist.
