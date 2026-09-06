# Lane-change safety & surround awareness — scope assessment

## Cameras: forward-only (no rear/side)

The comma 4 has three cameras, all used — but all **forward-facing**, one direction:

- **Road camera** — main forward (lane geometry + lead).
- **Wide road camera** — wide-angle forward; captures the *front* adjacent lanes.
- **Driver camera** — faces the driver (DM), not the road.

There is **no rear-facing camera and no side camera**. Openpilot's "surround" is
therefore **front-hemisphere only**. It cannot see a car directly behind or closing in a
blind rear quarter — that is the exact gap the rear corner radars fill (and which the
rear radar keeps *inside* the ADAS ECU, not on a bus openpilot reads — see VALIDATION.md
Drive 4).

## Lane model: already outputs front-flanking vehicles

The driving model (`ModelDataV2` → `leadsV3`) tracks **multiple** vehicles, each with:

- `x`, `y` — relative longitudinal + **lateral** position (device frame)
- `v`, `a` — absolute speed + acceleration
- `prob` — lead probability

So openpilot's model *does* see vehicles in the front-left / front-right adjacent lanes
(front-hemisphere flanking), with lateral offset and velocity. This is the realistic basis
for a **vision-driven lane-change "ahead" gate**: "is there a car in the target lane
ahead at what closing speed."

Caveat: it is the model's *prediction* (not radar fusion) — must be validated on-car
before trusting for lane-change safety.

## The rear-hemisphere gap (unresolved, and why)

- Rear close-rate is the one thing a safe lane-change genuinely needs and openpilot cannot
  self-generate: no rear camera, and the rear radar's doppler stays internal to the ADAS ECU.
- The BSD presence booleans (`leftBlindspot`/`rightBlindspot`, now fixed via `enableBsm`)
  give "car alongside right now" but **not** "car closing fast from behind."
- Forcing HDA2 "always on" does **not** expose the rear radar to openpilot — the ADAS ECU
  fuses it internally and only emits the HDP-gated HMI layer; and openpilot suppresses
  that ECU ('no lane lines') to win steering. HDA2 + openpilot steering are **mutually
  exclusive** on this architecture (see Longitudinal_plan.md).

## Net position

| Layer | Available to openpilot today | Source |
|---|---|---|
| Forward lead + flanking (ahead, lateral) | ✅ (model `leadsV3` x/y/v) | wide front camera |
| Blind-spot presence (alongside) | ✅ (`left/rightBlindspot`) | BSD corner radars → 0x1BA |
| Rear closing-velocity | ❌ (not on any bus) | trapped in ADAS ECU |

**Realistic safe-lane-change gate now:** vision `leadsV3` (ahead) + BSD presence flags
(alongside). **Remaining gap:** true rear closing-vehicle — needs the deferred
angle-steering/HDA2 integration port, or additional hardware; not software-solvable today.

## Note on the vision model (to validate later)

`leadsV3` flanking data is the model's prediction. Before using it as a lane-change gate,
confirm on-car that a passing/alongside car produces a plausible `y`/`v` in `leadsV3`
during a normal drive — same controlled-capture idea as the lead-follow work.
