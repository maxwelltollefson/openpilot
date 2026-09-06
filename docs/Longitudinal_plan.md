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

3. **Lead sensing — RESOLVED (2026-09-06, from controlled lead-follow route 09bea0550a):**
   - `SCC_CONTROL.ACC_ObjDist`/`ACC_ObjRelSpd` are **sentinel** on the Carnival HEV
     (204.6 m / +34.6 m/s) — the ADAS ECU fuses the radar/camera internally and only
     emits `aReqValue`, never the per-object lead.
   - The camera `FR_CMR_03_50ms` lead and the MRR20 radar (`0x180`/`0x181`/`0x185`)
     also do NOT expose a decodable lead object (`0x181` is a scan-sweep frame; `0x180`
     word16 is CRC+counter with zero payload).
   - **The lead range IS available in `CCNC_0x162.LEAD_DISTANCE` (69|11, 0.1 m)** — the
     CCNC cluster's own lead rendering. Validated against a confirmed "lead 2-3 s ahead,
     with a slowdown": reads 34 m → 15 m while the lead braked, and closing velocity
     −2.0 m/s derived as d(DISTANCE)/dt. This is the ADAS ECU's *fused* lead (camera +
     radar), which is the authoritative target — better than raw radar for a longitudinal
     controller.
   - Implemented: `RadarInterfaceExt` reads the Carnival lead from `CCNC_0x162.LEAD_DISTANCE`
     (validity via `LEAD` state) and derives `vRel` from the distance time-series, feeding
     the standard `radard → leadOne → create_acc_control` pipeline.

**Sensing is now solved (lead distance + closing velocity from `CCNC_0x162`); the
actuation channel (`aReqValue`) is proven. Remaining: on-car validation of the two
together.**

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
