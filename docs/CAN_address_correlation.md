# Carnival HEV — CAN Address Correlation (empirical, from 11 rlogs)
#
# All addresses observed on the live car, mapped to DBC message name where known,
# classified by function. Source: aggregation of routes 00000001/00000006/00000007/00000009
# (maxwelltollefson fork) + 00000000 (ccdunder reference). Bus = panda src & 0x7.
#
# NOTE on frequency: n is total frames across ~11 routes. Approx rate = n / (routes * seg_len).
# "Always 50Hz-ish" = present every ~20ms; high-volume = core safety/dynamics messages.

## CORE DYNAMICS / SAFETY (ECAN bus 1, ~50-100Hz) — already decoded & used
0x045  GEAR                        gear
0x04A  IMU_01_10ms                 IMU/gyro (10ms)
0x060  ESP_STATUS                  stability
0x065  BRAKE                       brake pressure/pedal
0x0A0  WHEEL_SPEEDS                wheel speeds (vEgo)
0x0EA  MDPS                        steering motor: torque/angle/AciPluginSta
0x100  ACCELERATOR_BRAKE_ALT       accelerator (ICE path; bus0/2)
0x105  ACCELERATOR_ALT             accelerator (hybrid gas; bus1)
0x11A  FR_CMR_01_10ms              camera 10ms
0x125  STEERING_SENSORS            steering column angle+rate (wraps past ±180!)
0x12A  LFA                         LFA steering (HDA1 path)
0x130  GEAR_SHIFTER                gear
0x175  TCS                         traction/cruise/ACC enable
0x1A0  SCC_CONTROL                 stock ACC state
0x1AA  CRUISE_BUTTONS_ALT          cruise buttons (Carnival uses ALT)
0x1CF  CRUISE_BUTTONS              (standard; NOT used by Carnival)
0x1E0  LFAHDA_CLUSTER              cluster steering icon
0x413  BLINKERS                    turn signals
0x411  DOORS_SEATBELTS             doors/seatbelt

## STEERING (LKAS) — the ADAS ECU path
0x110  LKAS_ALT                    steering cmd: StrTqReqVal + ADAS_StrAnglReqVal (bus0/2)

## CAMERA / CCNC CLUSTER (bus 1, ~20-50Hz)
0x160  ADRV_0x160                  ADAS DRV keepalive
0x161  CCNC_0x161                  cluster HUD (CCNC)
0x162  CCNC_0x162                  cluster HUD (CCNC)
0x1B5  FR_CMR_03_50ms              camera 50ms (lane/lead)
0x1BA  ADAS_CMD_50_50ms            BSM blindspot flags (BCW_Lt/RtIndSta)
0x1DA  ADRV_0x1da                  ADAS DRV
0x1E5  BLINDSPOTS_FRONT_CORNER_1   blindspot (front-corner)
0x1EA  ADRV_0x1ea                  ADAS DRV
0x1F0  FR_CMR?                     16B 20Hz (camera-related, unverified)
0x1FA  FR_CMR_02_100ms             camera 100ms (speed-limit 0x1fa)
0x200  ADRV_0x200                  ADAS DRV
0x216  RADAR_0x216                 radar
0x240  RADAR_0x240                 radar track
0x345  ADRV_0x345                  ADAS DRV keepalive
0x362  CAM_0x362                   camera (LKA steering alt)
0x36A  BLINDSPOTS_FRONT_CORNER_2   blindspot (front-corner)

## RADAR (front MRR20)
0x180  CAM_0x180                   radar header (8B) -> actually the MRR20 lead msg
0x181  CAM_0x181                   radar points (32B, sparse ~20Hz)
0x185  CAM_0x185                   radar

## BODY / COMFORT (bus 1, low rate) — not needed for driving
0x47F  HVAC_TOUCH_BUTTONS
0x4D8  CLUSTER_INFO
0x4EB  LOCAL_TIME2
0x4F0  LOCAL_TIME

## UDS / DIAGNOSTIC / FINGERPRINT (low count, query-response)
0x730  ADAS ECU (0x730) tester present
0x7C4  fwdCamera query
0x7D0  fwdRadar query
0x7B7  cornerRadar ECU query  <-- CORNER RADAR ECU, only fingerprint (n=23), never streams

## J1939 / TRANSPORT (0x18DAxxxx) — ECU firmware query responses, not driving data

## === CORNER RADAR HUNT — the unresolved targets ===
# Confirmed NOT corner radar on Carnival:
#   0x100 (accelerator), 0x200 (ADRV), 0x101/0x201 (Mando points) ABSENT
# Open candidates (unmapped, need passing-car drive to disambiguate):
#   0x7B7 cornerRadar ECU — idle so far (fingerprint only); does it stream when car alongside?
#   Possible CCNC rear-lateral point source: look for 20Hz repeating distance+relvel+azimuth
#   triplet in the unmapped bus1 8-byte cluster around 0x38C-0x3E6 / 0x40x-0x49x range.
#   (These are high-ish rate but small; several are likely TPMS/body, need payload correlation.)
