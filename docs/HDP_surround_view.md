# Surround-view (HDA2/HDP) flanking-vehicle data

## What drives the "3 lanes with cars left/right/behind + velocity" display

The full HDA2 surround view is rendered from **`CCNC_0x162`** (`BO_ 354`, address
`0x162`, 32-byte CCNC cluster message). It carries a up-to-6-object surround track:

| Signal | Start|Len | Meaning |
|---|---|---|---|
| `LEAD` / `LEAD_DISTANCE` / `LEAD_LATERAL` | 64 / 69 / 80 | 5 / 11 / 7 | forward lead + range (0.1 m) + lateral offset |
| `LEAD_ALT(_DISTANCE/_LATERAL)` | 88 / 93 / 104 | — | 2nd forward lead |
| `LEAD_LEFT(_DISTANCE/_LATERAL)` | 112 / 117 / 128 | — | left-flank vehicle |
| `LEAD_RIGHT(_DISTANCE/_LATERAL)` | 136 / 141 / 152 | — | right-flank vehicle |
| `LEAD_LEFT_REAR(_STATUS/_DISTANCE/_LATERAL)` | 167 / 175 / 182 | — | left-rear (behind) |
| `LEAD_RIGHT_REAR(_STATUS/_DISTANCE/_LATERAL)` | 196 / 197 / 205 | — | right-rear (behind) |

Each object has a distance (meters) + lateral offset (meters) + status. The cluster's
displayed velocity is derived from the ADAS ECU's tracking of these distances over
time (doppler from the rear corner radars / front MRR20), and the `DISTANCE_CAR` /
`DISTANCE_SPACING` / `DISTANCE_LEAD` signals drive the color/box display.

## Gating — full HDP only

Empirically (from 11 rlogs): `LEAD_DISTANCE` is populated whenever a lead car is
present, but `LEAD_LEFT/RIGHT/LEFT_REAR/RIGHT_REAR` are **always 0** in normal driving.
They only populate when **HDP (Highway Driving Pilot, "cyan" `HDA_ICON=5`) is active** on
a qualified highway — because the ADAS ECU only enters full surround tracking when it is
fed the navigation ADAS-map data the camera requests via `FR_CMR_ReqADASMapMsgVal`
(`H_U_NAVI_V2` curvature/road-type feed from the head unit).

## Implication for Tier-2 / surround awareness

Compared to the corner-radar finding: the flanking/rear-vehicle *presence + distance +
lateral lane* data the autonomous-pass gate wants is **already on the CAN bus in
`CCNC_0x162`** — no corner point-cloud decode required. The catch is it is gated on HDP
mode. Off-HDP, only BSD presence booleans (`ADAS_CMD_50_50ms`) are available.

## Can HDP be force-triggered off a non-qualified road?

Not practically. The gate is **navigation-map data**, not a CAN status bit you can flip:
- `FR_CMR_ReqADASMapMsgVal` = the camera asking the head unit for `H_U_NAVI_V2` ADAS-map
  messages (curvature, road type, lane geometry).
- On a non-mapped road the nav unit does not provide that feed, so the ADAS ECU never
  reaches HDP. There is no "force HDP" input signal (only `HDA_ICON`/`FAULT_HDP` status).

Spoofing the `H_U_NAVI_V2` map feed + matching the nav unit's GNSS position agreement is
deep, fragile reverse-engineering — not worth it when a real qualified-highway drive is
one trip away.

## Capture required to decode the velocity semantics

- One drive in **full HDP ("cyan") mode on a qualifying interstate**, with cars
  alongside / behind, full rlog.
- Then decode `CCNC_0x162` `LEAD_*` fields vs. time to confirm: distance, lateral, and
  whether velocity is explicit (a companion field not yet named) or derived (Δdistance/Δt).
