# Validation Checklist — Kia Carnival 2025 HEV (CCNC) fork

Run through this on your **first logged drive** after the comma 4 returns from service.
Each item confirms one thing that could not be verified without the car. Work top to
bottom; the highest-value checks are first.

## Before you drive

- [ ] Install via `installer.comma.ai/maxwelltollefson/openpilot` → branch
      `kia-carnival-2025-hev`.
- [ ] Confirm the car **fingerprints correctly**: on the device, check it identifies as
      `Kia Carnival Hybrid 2025` / `Kia Carnival Hybrid (with HDA II) 2025` — *not* a
      generic "dashcam only" or a CAN/CABLING error. If it mis-identifies, stop and grab
      the fingerprint log before driving.
- [ ] **Steering-path confirmation (settle torque-vs-angle definitively)**: in the rlog,
      check whether `0x50`/`0x110` appears on the camera bus (→ `CANFD_LKA_STEER_MSG`, the
      HDA2 ADAS-ECU path) and confirm the `AciPluginSta`/angle-control state the car
      actually reports. This replaces `acidofrain`'s unverified "torque-steered" inference
      with your own car's truth. See `PORTING.md`.
- [ ] Enable **"Record and Upload Driver Camera"** + **route upload** so logs are
      preserved (see the sunnypilot "Share a Route" guide).

## Drive 1 — core connectivity & cluster (the essentials)

- [ ] **Lateral / steering works** — engage LKA/LFA and confirm the car steers (this is
      the `LKAS_ALT`/`LFA` angle-request path; it should feel like stock HDA2 or better).
- [ ] **No boot errors / on-screen faults** — no "check cabling", "CAN signal" errors, no
      unexpected disengages. (`UNSUPPORTED_LONGITUDINAL` means longitudinal is hidden, so
      you should see *no* longitudinal options — that's expected, not a bug.)
- [ ] **CCNC cluster UI renders** — lane lines, LFA icon, set-speed, and (if supported)
      lane-change-assist arrows + curvature animation appear on the cluster.
- [ ] **Blind-spot (BSM) indicators** light up when a car is alongside.

## Drive 2 — the two "workaround" capabilities

- [ ] **Speed-limit sign reading** (`0x1fa`): drive past a posted-speed-limit sign and
      note whether the HUD shows a *camera* speed-limit badge. This tells us if the
      Carnival camera emits `0x1fa` (sign reading) or only map data works.
- [ ] **ICBM / Speed Limit Assist**: enable *Settings → Cruise → Intelligent Cruise
      Button Management*. Drive toward a lower speed zone and confirm the **set-speed
      actually steps down** (it'll be coarse, ~1 mph per ~0.2 s, stepping the stock ACC).
      This is the critical "does stock ACC latch synthetic 0x1AA presses?" question.

### ICBM step-rate + SLA auto-set-validation (high value)

The car's *native* HDA2 auto-sets speed on sign changes; openpilot replicates this via
**Speed Limit Assist (policy) + ICBM (button actuator)** — both already wired to the
`0x1FA` camera sign. The open question is whether ICBM's button cadence actually
achieves the target promptly (vs. the car's "hold = 5 mph" native behavior).

- [ ] **Rate check**: with ICBM active, time how long a sign change (e.g. 55→35) takes to
      fully step the set-speed. If it's much slower than ~5 mph/s, ICBM is being throttled.
- [ ] **Counter/latch check**: confirm the ECU accepts every `0x1AA` `res_accel`/`set_decel`
      press. The ALT_BUTTONS counter-cycling pattern (`[1,1,0,None]` every 4th frame) may
      not match what the Carnival's CCNC ECU expects, causing *rejected* presses and a
      ~1 mph/s throttle (vs. the intended ~5 mph/s). A preserved rlog of the button frames
      lets us diff ICBM's counter pattern against the car's native hold.
- [ ] **SLA confirm**: verify Speed Limit Assist actually *sets* (not just suggests) the
      new posted speed, using the `SpeedLimitOffset` (fixed/%) setting as the target.

> This is the same root cause as the "hold button = 5 mph" native behavior: ICBM must
> replicate auto-repeat, but its cadence + counter acceptance on the ALT_BUTTONS (0x1AA)
> path is unvalidated. Fixing this makes both ICBM stepping *and* SLA sign-following fast
> and reliable, matching native HDA2. (True *instant* set-speed change still needs real
> longitudinal.)

## Drive 3 — longitudinal data capture (the big one)

This is the single most valuable thing you can produce for yourself *and* the community
(it unblocks true longitudinal on this car).

- [ ] Record a **20–30 min route** that includes: engage/disengage several times,
      stop-and-go in traffic behind a lead car, and a couple of ACC accel/decel events.
- [ ] Confirm the route has **full rlogs uploaded** (rlogs, not just qlogs) and is
      **preserved + public** in comma Connect.
- [ ] Note the **MRR20 radar tracks** — on the UI, confirm the radar plot shows lead
      vehicles (validates the 0x180/0x184 signal scaling I ported from PR #351).

## Drive 4 — corner/side-radar (unlocks Tier 2 autonomous pass)

**DEFINITIVE FINDING (2026-09-06) — presence-only BSD; no rear-corner radar point
cloud is exposed on the CAN bus.** Confirmed with a **real alongside-vehicle capture**
(`00000003--77d1519272`, ccdunder route; `BCW_RtIndSta` fired for 147 frames with a car
on the right). See `docs/CAN_address_correlation.md`.

- **Confirmed with alongside-vehicle evidence:**
  - **`0x7B7` (cornerRadar ECU): zero frames the entire route** — it never transmits
    object data, even with a car alongside. Fingerprint-time UDS handshake only.
  - `0x1E5` / `0x36A` (`BLINDSPOTS_FRONT_CORNER_1/2`): ~20 Hz status/envelope frames
    (checksum+counter+constants); **no range/velocity/azimuth object fields**.
  - `0x101`/`0x201` (Mando point messages): absent (front-only MRR20 radar `0x180/0x181`).
  - The **only** blind-spot output is `ADAS_CMD_50_50ms` (`0x1BA`) → `BCW_Lt/RtIndSta`
    **presence booleans**.
- **Physical part:** rear corner radars `99150-R0510` (doppler-capable — they drive
  BCA/RCCA including closing-velocity *internally*), but that velocity is used inside
  the ADAS ECU for the cluster alert + brake and is **not** re-published as a raw point
  stream on any bus openpilot reads.
- **Conclusion (final):** Tier-2 autonomous pass **cannot** use rear-radar range+velocity
  (it doesn't exist on the CAN bus). It can use BSD presence booleans + the vision model
  (which sees lead/adjacent vehicles). No further corner-radar reverse-engineering to do.

**Related fix in this fork:** `enableBsm=True` for the Carnival HEV — the auto-detect
(`0x1ba in fingerprint`) was False (0x1BA absent from the startup fingerprint), so
`leftBlindspot`/`rightBlindspot` silently never populated. The BSM indicators now surface
correctly (verified against the alongside-vehicle rlog).



## Drive 5 — DAW "take a break" suppression capture

The car's own Driver Attention Warning pops "Consider Taking a Break" on the cluster
because openpilot steering means the driver isn't moving the wheel. See
`docs/DAW_suppression.md` for the full investigation.

- [ ] Drive hands-off (openpilot steering) long enough for the **car's** "take a break"
      cluster popup to appear (not openpilot's own alert — the dashboard one).
- [ ] Record a preserved rlog of that moment.
- [ ] In cabana, confirm the Carnival's DAW message/source (camera → cluster) and the
      `DAW_WrnMsgSta` (`=1` "Rest Recommend") equivalent.
- [ ] Identify which message openpilot re-sends that carries the DAW warning field, so we
      can test forcing it to 0 while watching for high-beam / LKAS / DAW-settings regressions
      (the known ECU-conflict side effect on the Palisade/Telluride platform).

## If something misbehaves

| Symptom | Likely cause | Next step |
|---|---|---|
| "Check cabling" / CAN timeout | Undecoded CAN signal (known community issue, ~6 users reported on 2026 Carnivals) | Capture the failing route; the rlog will show which message |
| ICBM does nothing | Stock ACC not latching 0x1AA | Grab a route with ICBM on; revert just the ICBM commit (`44337abd3`) if needed |
| Cluster UI blank / partial | `FR_CMR_03_50ms` not present on Carnival camera | Falls back gracefully — confirm via the `msg_1b5` presence in the rlog |
| Steering feels off | Torque tuning needs per-car adjustment | Note it; the tune points live in `torque_data/override.toml` + steer-delta in `values.py` |

## How to share results back

- **Route ID:** post the public route ID in the sunnypilot forum threads ("ccNC Port",
  "Support for newer vehicles with Angle Steering (LFA2)") and/or to `acidofrain` and
  `iwilliamlee` — both are actively looking for exactly this Hybrid data.
- **To me / this fork:** drop the route ID here and I can decode the longitudinal-relevant
  CAN traffic (ADRV SCC keep-alive bytes, `0x1FA`, `0x1AA` latching) to finish the
  camera-SCC longitudinal path.
