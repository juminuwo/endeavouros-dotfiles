# Imoto One-Pager Workflow

## Source Paths

- Vault root: `/home/howis/Documents/online-personal/Imoto Labs/`
- One-pagers: `/home/howis/Documents/online-personal/Imoto Labs/Discovery/One-Pagers/`
- Artifacts: `/home/howis/Documents/online-personal/Imoto Labs/Discovery/One-Pagers/Artifacts/`
- Messaging docs: `/home/howis/Documents/online-personal/Imoto Labs/Messaging/`

## Production Sequence

1. Read vault conventions and the relevant messaging doc.
2. Review existing one-pager drafts, `One-Pager Template.md`, and current artifacts.
3. Draft or revise markdown copy with the approved one-pager sections:
   header, hero, problem, visual, value cards, first engagement, best fit, proof boundary, CTA.
4. Get or create visuals:
   - Use up-to-date product screenshots when available.
   - Generate demo graph/map visuals only when they reflect existing capability.
   - Crop visuals to the informative area; remove browser/app headers and text fragments that do not help the buyer.
5. Build an HTML source in `Artifacts/` from the skill template and shared CSS:
   - Bundled templates use `../one-pager.css` so they render correctly in place under `assets/templates/`.
   - Copy the selected template and `assets/one-pager.css` into `Artifacts/`.
   - In the copied HTML, change the stylesheet link to `one-pager.css` so it resolves beside the artifact.
6. Render a preview PNG and PDF with `scripts/imoto_onepager.py render`.
7. Inspect the preview and PDF render for:
   - one-page fit
   - readable text
   - no overlapping UI/text
   - visual clarity
   - prominent proof boundary
8. Validate with `scripts/imoto_onepager.py validate`.
9. Update `Artifacts/Artifacts.md` and the one-pager index links.

## Review Loop

Ask for feedback at the copy stage when claims, ICP, or CTA are unsettled. Move to HTML/PDF only after the copy and visual direction are stable.

When revising after PDF feedback, prefer changing the HTML/CSS and recropping visuals over shrinking text. The result should remain printable and readable.

## Commands

Render a page:

```bash
python config/agent-skills/imoto-one-pagers/scripts/imoto_onepager.py render \
  '/home/howis/Documents/online-personal/Imoto Labs/Discovery/One-Pagers/Artifacts/driver-shield-one-pager.html'
```

Validate all PDFs:

```bash
python config/agent-skills/imoto-one-pagers/scripts/imoto_onepager.py validate \
  '/home/howis/Documents/online-personal/Imoto Labs/Discovery/One-Pagers/Artifacts/'*-one-pager.pdf
```
