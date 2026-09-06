# Kia Carnival 2025 HEV — Porting Notes

This fork adds **2025 Kia Carnival HEV (CCNC)** support to sunnypilot for the
**comma 4**, on top of the **latest stable release** (`release-mici` =
`v2026.002.002`, commit `6a17f75c`, "sunnypilot v2026.002.002", 2026-08-06).

## Base

- **Base branch:** `release-mici` (`v2026.002.002`) — the latest stable sunnypilot
  release intended for the Comma 4 (C4, codename "mici"). This is the same commit
  `release-tizi` (C3X) points at.
- **Key structural fact:** in this release, `opendbc` and `panda` are **vendored
  in-repo** as subtrees (not git submodules). All vehicle logic therefore lives in
  `opendbc_repo/`; the main openpilot repo required no changes.

## Sources ported

1. **Vehicle support (connectivity + tuning):** [`ccdunder/openpilot`](https://github.com/ccdunder/openpilot),
   branch `kia-carnival-25-sp-dev` (tip `5093009` in its `opendbc` fork). The
   Carnival HEV work is a clean, linear chain of ~15 vehicle-specific commits.
2. **CCNC integration:** only the CCNC pieces required by the Carnival HEV. The
   vehicle is `flags=HyundaiFlags.CCNC`, so the CCNC cluster messaging
   (`CCNC_0x161`/`0x162`) and the associated safety whitelist are part of the port.
3. **BSM + `UNSUPPORTED_LONGITUDINAL`:** [`acidofrain/opendbc`](https://github.com/acidofrain/opendbc),
   branch `kia-carnival-2026-sx` — the 2026 Carnival SX (ICE, HDA2) sibling port.
   Two clean commits folded in: the `ADAS_CMD_50_50ms` BSM-subscription fix and the
   honest `UNSUPPORTED_LONGITUDINAL` platform flag.
3. **Full CCNC cluster UI:** the `create_ccnc` from sunnypilot's `ccnc-port` — the
   "beautiful UI" CCNC feature set: fault-free dash, lane-change-assist (LCA) icons and
   arrows, lane-line curvature + position animation, lane-departure steering-wheel
   vibration (`VIBRATE`), blind-spot indicators, and the nav/SLA/target icons. Requires
   the `FR_CMR_03_50ms` (msg_1b5) camera message; gracefully degrades to the basic
   subset if that message is not present on the Carnival.

## Deliberately excluded: LFA2 angle-steering *branch* (but note the nuance)

Two distinct things are often conflated, and it matters:

1. **Steering request architecture (what this fork actually uses):** On CAN-FD HKG cars the
   lateral command is an **angle request** — both `LKAS`/`LKAS_ALT` and `LFA` carry
   `ADAS_StrAnglReqVal` (steering *angle* request, capped ~176.7° / 119.9°). The steering
   **type/path** is decided at runtime by a bus-message check, not a hard-coded assumption:

   ```
   lka_steering = 0x50 in fingerprint[cam_can] or 0x110 in fingerprint[cam_can]
   ```

   - `0x50`/`0x110` present → `CANFD_LKA_STEER_MSG` (**HDA2 with ADAS ECU**): camera sends
     LKA steering, ADAS DRV ECU forwards it as LFA to MDPS.
   - absent → non-LKA (**HDA1**): camera sends LFA directly to MDPS.

   The Carnival is an **HDA2 car** and is therefore expected to take the `CANFD_LKA_STEER_MSG`
   path. There is no "torque-only vs angle-only" fundamental split in the message — the
   earlier shorthand "torque-steered" was imprecise and has been corrected here.

2. **The dedicated angle-steering implementation (`hkg-angle-steering-2025`):**
   There IS a mature, purpose-built angle-steering system for HKG cars — a whole branch
   family (`hkg-angle-steering-2025-new-controls`, `-prebuilt`, `-tici`, etc.). It sets
   `steerControlType = angle` for any car flagged `CANFD_ANGLE_STEERING`, backed by a full
   tuning framework (`AngleSteeringLimits`, torque-reduction-gain for driver override,
   `ANGLE_TORQUE_OVERRIDE_CYCLES`, speed-based smoothing matrix, etc.).

   **However, the Carnival is NOT in the angle set** — in that branch `KIA_CARNIVAL_4TH_GEN`
   carries `flags = RADAR_SCC` (no `CANFD_ANGLE_STEERING`), and there is **no Carnival HEV
   entry at all**. The angle cars are IONIQ/Kona/Sportage/Sorento/Santa Fe etc. (This is
   consistent with `acidofrain`'s `AciPluginSta = 0` report on the Carnival — the ADAS-ECU
   / LFA-forwarded variant where angle-ready steering was never confirmed.)

   So: angle steering is real and mature *in HKG generally*, but **not-yet-ported to the
   Carnival** (ICE or HEV). Adopting it is not a "revert/fold-in" — it would mean porting
   the `CANFD_ANGLE_STEERING` path + tuning framework to the Carnival HEV and validating
   it, which is novel, unproven-on-this-trim work. Real-world testing on this user's car
   showed both forks steering fine (both are torque-based), so torque is proven; angle is
   the theoretically-better-but-unvalidated option, to be A/B-tested only after the
   first-route fingerprint confirms steering readiness.

**Open, verifiable-from-the-first-route:** whether the Carnival HEV's camera bus actually
carries `0x50`/`0x110` (confirming `CANFD_LKA_STEER_MSG`), and whether `AciPluginSta=0`
holds for the HEV trim (it was reported for the sibling ICE SX, not verified for the HEV).
Both are fingerprint/rlog-verifiable and are queued in `VALIDATION.md`.

## What was ported (12 files, all in the vendored opendbc)

| File | Change |
|------|--------|
| `opendbc/car/hyundai/values.py` | `KIA_CARNIVAL_HEV_4TH_GEN` platform (mass 2253, wheelbase 3.09, steerRatio 14.23, `CCNC` flag); `HyundaiFlags.CCNC = 2**27`; `HyundaiSafetyFlags.CCNC = 1024`; steer-delta tune; fuzzy-whitelist entry |
| `opendbc/car/hyundai/interface.py` | `steerActuatorDelay = 0.35`; BSM disabled on Carnival HEV (ADAS-ECU limitation); CCNC safety-param wiring |
| `opendbc/car/hyundai/fingerprints.py` | Carnival HEV `fwdCamera`/`fwdRadar` FW versions + 2024 ICE FW revisions |
| `opendbc/car/fingerprints.py` | `KIA CARNIVAL HYBRID 4TH GEN` migration entry |
| `opendbc/car/hyundai/hyundaicanfd.py` | `create_buttons` ALT_BUTTONS (`CRUISE_BUTTONS_ALT`, `SET_ME_2`); `create_lfahda_cluster` CCNC; `create_ccnc`; Carnival ADRV magic bytes (`SET_ME_9 0x1`, `SET_ME_1C 0x8`, `SET_ME_E1 0x14`, `SET_ME_3A 0x80`) |
| `opendbc/car/hyundai/carstate.py` | CCNC `CCNC_0x161`/`0x162` capture + parser; `USE_ALT_LAMP` blinker detection |
| `opendbc/car/hyundai/carcontroller.py` | `create_ccnc` transmit; cruise-standstill resume for ALT_BUTTONS cars |
| `opendbc/safety/modes/hyundai_canfd.h` | CCNC safety param (`1024`) + `0x161`/`0x162`/`0x7C4`/`0xEA` TX whitelist; ALT_BUTTONS `0x1AA` TX support across all init branches |
| `opendbc/car/torque_data/override.toml` | `KIA_CARNIVAL_HEV_4TH_GEN = [1.95, 1.75, 0.12]` |
| `opendbc/car/tests/routes.py` | test route `6c0069dcd5bbb6c1/00000020--6b95507969` (HDA2) |
| `opendbc/sunnypilot/car/car_list.json` | two Carnival Hybrid 2025 entries |
| `docs/CARS.md` | two Carnival Hybrid 2025 rows |

## Deliberate deviations from the source branch (important)

The goal was a **clean, correct, compilable** result, not a byte-for-byte copy.
Three latent bugs in the `ccdunder` source were corrected rather than propagated:

1. **`values.py` steer-delta typo (double-`DOWN`) → FIXED as a transposition.** The
   source set `STEER_DELTA_DOWN` twice (`= 4` then `= 6`). The correct resolution is
   **not** "the second is `STEER_DELTA_UP`" — it is that the *intended* double of the
   CAN-FD base (UP=2→4, DOWN=3→6) is `STEER_DELTA_UP = 4, STEER_DELTA_DOWN = 6`.
   An earlier pass incorrectly set UP=6/DOWN=4, which inverted the HKG safety convention
   (DOWN must be ≥ UP so steering force can be shed faster than it is added). Final fix
   (`2cfd26099`) restores UP=4/DOWN=6.
2. **`create_ccnc` duplicate message** — the source appended `CCNC_0x161` twice;
   the second must be `CCNC_0x162`. Fixed.
3. **Undefined DBC signals** — the source referenced `SET_ME_A8`, `SET_ME_2C`,
   `SET_ME_56`, `SET_ME_F7`, `SET_ME_9F`, `SET_ME_10` and message `ADRV_0x38C`
   in Python, but these do not exist in any DBC (generator or generated) in the
   branch — they would raise at packaging time. These appeared to be uncommitted
   local magic bytes. The *valid* DBC-value changes were kept (they are the real
   Carnival tuning); only the phantom signals/messages were dropped. Adding
   correct bit layouts for them would require CAN captures from the car and was
   intentionally left out rather than invented.

## Safety notes

The Carnival HEV is CCNC + camera-SCC + ALT_BUTTONS, so the panda safety model
needed two additions that were missing from the stable base:

- A `HYUNDAI_PARAM_CCNC = 1024` flag and a `hyundai_ccnc` runtime flag, wired from
  `HyundaiSafetyFlags.CCNC` in `interface.py`.
- Whitelisting of the CCNC cluster messages (`0x161`, `0x162`) and the ALT_BUTTONS
  cruise-button message (`0x1AA`) for TX, across every steering/longitudinal branch.

Without these, the panda would block the CCNC HUD messages and/or the alt-button
cruise buttons, and the car would not function.

## BLOCKER: panda firmware (`main.bin`) is stale — MUST be rebuilt & committed

Diagnosed 2026-09-05 against route `01e8c55a8200bc9f|00000006--df5863984b`. The
Carnival HEV gets a persistent `controlsMismatch` (92 events) from
`safetyRxChecksInvalid=true`, which flips on the instant the safety mode applies and
never clears.

**Root cause:** the committed panda firmware
`panda/board/obj/panda_h7/main.bin` is frozen at the base release commit
`6a17f75c6` (sunnypilot v2026.002.002). That release's `hyundai_canfd_init` LKA
branch hardcodes `HYUNDAI_CANFD_STD_BUTTONS_RX_CHECKS(1)` with the comment
"Does not use the alt buttons message" — i.e. it RX-checks `0x1CF`, which the
Carnival HEV **never sends** (it sends `0x1AA` alt buttons). The unfulfillable
`0x1CF` check leaves `msg_seen` unset → `valid_checksum=false` →
`safety_rx_checks_invalid=true`. The fix commits:

- `032c02a4a` added `hyundai_canfd_lka_steer_msg_alt_buttons_rx_checks`
  (`HYUNDAI_CANFD_ALT_BUTTONS_RX_CHECKS(1)` = `0x1AA`) to `hyundai_canfd.h`.
- `5ef4d641e` review fixes on top of it.

…but **neither rebuilt `main.bin`**, and `pandad.py` auto-flashes the panda from
this bundled binary on every boot (`selfdrive/pandad/pandad.py` `flash_panda()`).
This is why switching to ccdunder "just works" (its `main.bin` was built after the
`0x1AA` fix) while this fork mismatches.

**Fix:** rebuild `panda/board/obj/panda_h7/main.bin` from the current
`opendbc_repo` safety source and commit it. Requires the openpilot Linux/Docker
build toolchain (`scons` + `arm-none-eabi-gcc`), NOT the Windows host. In the
sunnypilot Docker image: `scons -j$(nproc)` from the repo root (or the release CI
job that produces panda firmware), then commit the resulting `main.bin`.

**Verification (from the rlog, all confirmed):** `carParams` = `hyundaiCanfd`,
`safetyParam=178` (`LKA_STEER_MSG` 16 | `LKA_STEER_MSG_ALT` 128 | `ALT_BUTTONS` 32 |
`HYBRID_GAS` 2) — correct. Every message the panda needs is present on bus 1 with
valid 8-bit counters and matching CRC-16 checksums; the sole failure is the stale
firmware's phantom `0x1CF` requirement.

## Verification performed

- `py_compile` and full `ast.parse` on all 8 modified Python files — clean.
- `car_list.json` parses as valid JSON; `override.toml` parses as valid TOML.
- All `KIA_CARNIVAL_HEV_4TH_GEN` references are consistent across
  values/fingerprints/interface/test-routes/torque-data/car_list.
- Every CCNC signal referenced by `create_ccnc` exists in the generator DBC.
- The safety header is brace/paren-balanced and every added macro/array is
  declared and used exactly once.

A full openpilot build (which generates capnp bindings and compiles the safety
model) requires the Linux build toolchain and was not performed on this host; the
user should run the standard sunnypilot CI/build on the device or in Docker to
confirm, then test on the car.

## Install

Push this branch to a GitHub fork, then on the comma 4:
**Settings → Software → Custom Software → enter the fork URL**
(e.g. `https://github.com/<you>/sunnypilot` with branch
`kia-carnival-2025-hev`), or use the install URL
`installer.comma.ai/<your-username>/sunnypilot` pointing at this branch.

## Flag-collision landmine (documented for future angle-steering work)

`CCNC` and the angle-steering lineage's `CANFD_ANGLE_STEERING` both use the **same bits**
(`HyundaiFlags 2**27` + `HyundaiSafetyFlags 1024`). A naive fold-in of angle steering would
silently corrupt `CCNC`. Re-home one to a free bit first (this fork uses `2**28` for
`CANFD_RADAR`; free bits include `2**23`, `2**26`, and ≥ `2**29`). Full detail in
`docs/HKG_sibling_research.md`.
