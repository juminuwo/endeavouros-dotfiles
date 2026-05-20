# Driver Shield procurement messaging notes

Use when updating `Imoto Labs/Messaging/Driver Shield.md`, especially the `Appendix: Pilot rig cost basis (internal)` / `Current procurement state` section.

## Current framing preference

The Driver Shield procurement story should present the **fleet-budget new-build path** as the default option for fresh Pilot builds:

- Default path: full Pi stack + ELP ready-made waterproof `USBFHD06H` cameras.
- Approximate internal cost basis: `~£828 ex-shipping`.
- Rationale: cheaper, faster, less DIY-looking, avoids separate 4K cameras + custom waterproof housing work.
- Trade-off to state honestly: IMX322/1080p ceiling and roughly 20–30% night SNR penalty versus the 4K IMX415 stack, accepted for default builds because install simplicity and cost matter more at this stage.

The more expensive 4K builds should be framed as **other paths / reference paths**, not the default:

- 4K reference / DIY-housing build: `~£1,167 ex-shipping`.
- 4K + EcoFlow mid build: `~£1,292 ex-shipping`.
- Use these when the goal is best sensor quality, side-by-side comparison, or longer parked-mode runtime.

Avoid reverting to older wording like “Pilot vehicle #1 default build” for the 4K + DIY-housing path unless the user explicitly changes direction.

## USB extension cable procurement note

For Driver Shield vehicle camera cable runs, the docs point to **active USB 2.0 extension cables**, not passive long cables.

Documented spec:

- USB 2.0 active extension / repeater cable.
- 5 m default length for rear camera + far-side passenger-car runs.
- 5–15 m active USB 2.0 for longer box-truck-style runs.
- Prefer good shielding and, where stated, heavier power conductors such as 20 AWG.
- Topology: camera/camera cable → active USB 2.0 extension → powered Sabrent hub → Pi.
- Avoid cheap passive 5 m extensions, charge-only cables, and chains of passive extensions.

Amazon UK examples found in-session:

- Preferred value pick: Cable Matters Active USB Extension Cable 5m, USB-A male to USB-A female, active USB 2.0, 480 Mbps, ASIN `B07VYVWRNN`, seen at `£13.99`.
- Conservative premium pick: StarTech.com 5m USB 2.0 Active Extension Cable, model `USB2AAEXT5M`, ASIN `B00K7YI7W2`, seen at `£36.35`.
- Cheaper acceptable fallback: CSL 5m USB 2.0 active repeater extension, ASIN `B00S7SCNKW`, seen at `£9.99`.

Recommendation pattern: buy 2× for first passenger-car Pi test; use for rear + farthest side. Buy 4× if maximum routing flexibility matters and return unused ones.
