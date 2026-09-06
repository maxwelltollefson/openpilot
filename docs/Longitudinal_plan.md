# Longitudinal Control Plan — Kia Carnival HEV (CCNC/HDA2)

Evidence base: 11 rlogs (routes 00000000/00000001/00000006/00000007/00000009 +
ccdunder reference). Decoded with the fork's capnp + DBC.

## What the rlogs prove (the good news)

1. **Stock ACC engages and commands acceleration on the CAN bus.**
   In `seg3` (maxwelltollefson fork, driving): `SCC_CONTROL` (0x1A0) showed
   `ACCMode=2` ("driver_override"/engaged) for 404 samples, and **`aReqValue`
   went non-zero (up to +0.31 m/s²)** — i.e. the ADAS ECU actively commands
   longitudinal acceleration via `SCC_CONTROL.aReqValue`.

2. **The longitudinal command signal is known and live.**
   `SCC_CONTROL` (BO_ 416, 0x1A0): `aReqValue : 128|11 (0.01,-10.23) m/s²`,
   `ACCMode : 68|3` (0=off,1=enabled,2=driver_override,3=fault,4=cancelled),
   `CRUISE_STANDSTILL : 76|1`, `VSetDis : 103|8`, `ObjValid : 46|1`.
   `ACC_REQ : 68|1` in the companion ACC-request message.

3. **Lead sensing — corrected/refined (2026-09-06, from lead-vehicle rlogs):**
   - `SCC_CONTROL.ACC_ObjDist`/`ACC_ObjRelSpd` are **always at the invalid/max
     sentinel** (204.6 m / +34.6 m/s) on the Carnival HEV, even with a lead
     present (3,000/3,000 frames in `seg3`). The ADAS ECU tracks the lead
     *internally* and only outputs `aReqValue`; it does NOT expose per-object
     range/velocity in `SCC_CONTROL`.
   - The camera `FR_CMR_03_50ms` (0x1B5) lead field (`ID_CIPV`/`Relative_Velocity`/
     `Longitudinal_Distance`) is also 0/"no lead" in every route.
   - **The lead range+closing-velocity therefore live in the MRR20 radar `0x181`**
     (32-byte track cluster), which is present (~20 Hz) but **undecoded**. Byte-
     statistics identify byte 15 + 17 as the primary high-variability data fields
     (likely range/velocity) and bytes 13/19/20/22/23 as secondary/lateral/azimuth,
     but exact scaling is unresolved (needs a controlled lead-at-known-distance capture).

**Implication for longitudinal sensing:** the enabled camera-SCC path reads lead
from `SCC_CONTROL` (sentinel on Carnival), so with the current wiring openpilot has
no lead target — follow-distance/stop-and-go will be incomplete until the MRR20
`0x181` is decoded and a Carnival radar-interface feeds `lead_data` into
`create_acc_control`. The actuation channel (`aReqValue`) works; the sensing needs
the MRR20 decode.

## The blocker (unchanged, now precisely located)

Longitudinal = **actuator path** + **sensing**. Sensing is ready (lead range +
closing velocity). The actuator path — sending `SCC_CONTROL.aReqValue` *and having
the car act on it instead of its stock controller* — is the open part. On the CCNC
family this is unvalidated because it requires suppressing the stock ACC/SCC source
and winning the ADAS-ECU arbitration, which none of the three known HKG paths has
done for this trim yet.

## Candidate actuator paths (in order of increasing difficulty)

### Path A — Camera-SCC takeover (matches this fork's existing wiring)
The Carnival HEV is camera-SCC (camera sends SCC on bus 1). Approach:
1. **DONE — arbiter identified:** `SCC_CONTROL` (0x1A0) arrives from the STOCK car on
   **bus 1** (ECAN) in every driving rlog, and its `aReqValue` goes non-zero (up to
   +0.31 m/s²) during ACC engagement — the stock controller (camera/ADAS ECU on bus 1)
   is the SCC arbiter and actively commands acceleration through this signal.
2. Suppress the stock SCC (communication-control disable of the camera SCC, or "block & replace").
3. Send our own `SCC_CONTROL` with `aReqValue` + `ACCMode` + `ObjValid` on bus 1.

**Risk:** on camera-SCC cars, blocking the camera can also kill AEB/FCA. Requires
the same "block camera SCC, forward stock AEB" trick as other HKG camera-SCC cars.

### Path B — ADAS-ECU interceptor (`devtekve` PR #196, alpha)
Send `create_adas_drv_intercept_msg` to the ADAS ECU (0x730) to take longitudinal.
Status: alpha, "no one has long working yet" on CCNC/HDA2. Requires the R-connector
(ADAS ECU) or the "silence ADAS ECU via diagnostics" approach.

### Path C — Radar SCC
The Carnival uses MRR20 front radar (`0x180`/`0x181`), not the Mando radar `0x251`.
This path (disable radar `0x7D0`, send ACC) is the traditional HKG radar-SCC route
but is unvalidated for this MRR20 + CCNC combination and risks radar/AEB loss.

## Concrete next steps (in order, each de-risked)

1. **Instrument, don't guess.** Decode `SCC_CONTROL` (0x1A0) *source* (which src bus
   carries it: camera vs ADRV) in the driving rlogs (`seg3`/`seg4`/`seg5`). This tells
   us whether the camera or the ADAS ECU is the SCC arbiter — the first fork in the road.

2. **Prove `aReqValue` is the actuation channel.** In a stock-ACC-engaged rlog, correlate
   `aReqValue` against `vEgo` delta: when `aReqValue` ramps, does the car accelerate?
   (Confirms the car *obeys* this signal — it does today under its own ACC, but we need to
   confirm it's the *only* longitudinal authority, not a feedback echo.)

3. **Suppression test (Path A first).** On a bench/stationary captured drive, verify the
   stock SCC source can be silently disabled (communication-control) without tripping
   AEB/FCW faults. This is the highest-risk step and should be logged and reverted quickly.

4. **Minimal longitudinal pilot.** Add a `CCNC_CAMERA_SCC_LONG` flag + `create_scc` that
   sends `aReqValue` (clamped) with correct `ACCMode`/`ObjValid`, gated to low speed,
   behind the existing `UNSUPPORTED_LONGITUDINAL` until proven. Ship as *experimental*,
   AEB behavior watched on every drive.

5. **Validate on car, incrementally:** stop-and-go behind a lead car first (low risk),
   then ACC accel/decel, then higher speeds — each gated and reversible.

## What we should NOT do

- Don't re-implement longitudinal from scratch; reuse sunnypilot's existing HKG camera-SCC
  longitudinal code path and adapt the Carnival's message set.
- Don't enable it fleet-wide or silently; keep it behind a toggle + explicit opt-in until
  AEB/FCW behavior is confirmed safe.

## Realistic scope

This is **actuator validation work on the vehicle**, not more rlog decoding. The sensing
side is done. The plan is now: (1) identify the SCC arbiter, (2) prove the command channel,
(3) suppress stock cleanly, (4) pilot, (5) validate incrementally. Each step is small and
reversible; the on-car suppression + AEB regression testing is the genuine risk and effort.
