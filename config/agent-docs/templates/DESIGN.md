---
version: alpha
name: Project Design System
description: Agent-facing visual identity and design-system tokens for this UI repo.
colors:
  primary: "#1A1C1E"
  primary-hover: "#2B2F33"
  secondary: "#6C7278"
  tertiary: "#B8422E"
  neutral: "#F7F5F2"
  surface: "#FFFFFF"
  on-primary: "#FFFFFF"
  on-surface: "#1A1C1E"
  border: "#D7D2CA"
  error: "#B3261E"
typography:
  headline-lg:
    fontFamily: "Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: 32px
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0em"
  headline-md:
    fontFamily: "Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: 24px
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "0em"
  body-md:
    fontFamily: "Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0em"
  label-md:
    fontFamily: "Public Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "0em"
rounded:
  none: 0px
  sm: 4px
  md: 8px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
components:
  app-shell:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    padding: "{spacing.lg}"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label-md}"
    rounded: "{rounded.sm}"
    padding: "{spacing.sm}"
    height: 44px
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.sm}"
  status-error:
    backgroundColor: "{colors.error}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    padding: "{spacing.sm}"
---

# Project Design System

## Overview

Describe the product's visual posture, audience, and UI density here. Keep this
specific to the repo. A useful first version states whether the app is
operational, editorial, playful, analytical, or marketing-led, and what the
first screen should help users do.

Link detailed project UI standards here instead of duplicating them.

## Colors

Explain the palette by role, not decoration.

- **Primary:** Main structure, headings, and primary actions.
- **Secondary:** Metadata, subdued labels, and secondary information.
- **Tertiary:** Accent or product-specific semantic color.
- **Neutral:** Page canvas and quiet background.
- **Surface:** Cards, controls, and focused work areas.
- **Error:** Destructive, blocked, or invalid states.

## Typography

Document the font stack and hierarchy. Keep display type for true page-level
headings; use smaller, tighter type inside panels, cards, tables, and forms.

## Layout

Record spacing rhythm, max widths, breakpoints, touch targets, and density
rules. Prefer stable dimensions for repeated controls so labels, counts, and
hover states do not resize the layout.

## Elevation & Depth

State whether hierarchy comes from borders, shadows, color contrast, or spatial
grouping. Avoid adding decorative depth if the product should feel utilitarian.

## Shapes

Document corner radii and shape exceptions. Keep cards and controls consistent
unless a component has a clear established reason to differ.

## Components

List the shared component vocabulary and the states agents should preserve:
shells, headers, buttons, fields, tables, cards, banners, pills, navigation, and
dialogs.

## Do's and Don'ts

- Do use the token values above as the source for new UI work.
- Do update this file when shared visual tokens or component vocabulary changes.
- Do keep accessibility and responsive behavior explicit.
- Don't introduce decorative color without assigning it a role.
- Don't make a broad redesign while claiming to only document the current
  system.
