---
name: imoto-one-pagers
description: Create, revise, review, and export Imoto Labs customer-facing one-pager PDFs and sell sheets. Use when Codex is asked to make or update Imoto one-page collateral, A4 printable sheets, HTML/CSS-to-PDF artifacts, product screenshots, proof-boundary copy, or Discovery/One-Pagers vault materials for Driver Shield, Route Optimization, Predictive Maintenance, or similar Imoto offerings.
---

# Imoto One-Pagers

Build polished, claim-safe Imoto Labs one-page PDFs from product messaging docs through final A4 portrait HTML/PDF artifacts.

## Start Here

- Work in the vault: `/home/howis/Documents/online-personal/Imoto Labs/Discovery/One-Pagers/`.
- Read `/home/howis/Documents/online-personal/Imoto Labs/CLAUDE.md` and the relevant `Messaging/<Product>.md` before drafting customer-facing copy.
- Use `Discovery/One-Pagers/Artifacts/` for approved screenshots, generated previews, HTML sources, and PDFs.
- Do not put generated sell sheets in `Messaging/`; messaging docs are source material, not channel artifacts.
- Do not copy third-party PDFs/screenshots into the vault unless the user explicitly approves it.

## Workflow

1. **Ground the product and claims.** Read the messaging doc, existing one-pager drafts, and current artifacts. Identify forbidden claims and proof-boundary language before writing.
2. **Draft copy first.** Create or update the markdown one-pager for headline, subhead, problem, value cards, first engagement, best fit, proof boundary, and CTA.
3. **Select visuals.** Prefer current product/demo screenshots, dashboard graphs, route maps, evidence screens, or clean technical diagrams. Crop away app chrome, text fragments, and irrelevant UI when they weaken the page.
4. **Design in HTML/CSS.** Use A4 portrait by default, large readable type, varied layouts across products, and technology-forward visuals. Use `assets/one-pager.css` and one of the templates in `assets/templates/` as a starting point.
5. **Export and validate.** Render preview PNG and PDF with the helper script. Check the PDF at actual size, verify one-page A4 output, and scan extracted text for pricing/secrets patterns.
6. **Update artifact navigation.** Keep `Artifacts/Artifacts.md` and `One-Pagers.md` current when adding new generated assets.

Read `references/workflow.md` for the detailed production sequence, `references/product-rules.md` for product-specific claim rules, and `references/design-standards.md` for layout standards.

## Helper Script

Use `scripts/imoto_onepager.py` for repeatable rendering and validation:

```bash
python config/agent-skills/imoto-one-pagers/scripts/imoto_onepager.py check-deps
python config/agent-skills/imoto-one-pagers/scripts/imoto_onepager.py screenshot input.html output.png --width 1400 --height 900
python config/agent-skills/imoto-one-pagers/scripts/imoto_onepager.py crop input.png output.png '920x1000+0+240'
python config/agent-skills/imoto-one-pagers/scripts/imoto_onepager.py render one-pager.html
python config/agent-skills/imoto-one-pagers/scripts/imoto_onepager.py validate one-pager.pdf
```

The script expects Chrome, ImageMagick, and Poppler (`pdfinfo`, `pdftotext`, `pdftoppm`) to be available.

## Quality Bar

- The finished PDF is one A4 portrait page and readable when printed.
- The design looks like a polished sell sheet, not a markdown export or Word document.
- The visual explains the offer; it is not generic AI art, stock filler, or decorative clutter.
- The proof boundary is prominent.
- The CTA asks for a concrete first engagement.
- No internal BOM, procurement detail, credentials, pricing, or unsupported ROI/savings/accuracy/safety/insurance claims appear in the output.
