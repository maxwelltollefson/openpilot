from opendbc.can.parser import CANParser
from opendbc.car import structs, Bus
from opendbc.car.hyundai.hyundaicanfd import CanBus
from opendbc.car.hyundai.values import CAR, DBC, HyundaiFlags

import time

from opendbc.sunnypilot.car.hyundai.escc import EsccRadarInterfaceBase


class RadarInterfaceExt(EsccRadarInterfaceBase):
  msg_src: str
  trigger_msg: int
  rcp: CANParser
  pts: dict[int, structs.RadarData.RadarPoint]

  def __init__(self, CP: structs.CarParams, CP_SP: structs.CarParamsSP):
    EsccRadarInterfaceBase.__init__(self, CP, CP_SP)
    self.CP = CP
    self.CP_SP = CP_SP

    self.track_id = 0

    # Carnival HEV: SCC_CONTROL.ACC_ObjDist/ACC_ObjRelSpd are sentinel (204.6 m /
    # +34.6 m/s — the ADAS ECU tracks the lead internally and only emits aReqValue),
    # so the lead range lives in the CCNC cluster message CCNC_0x162.LEAD_DISTANCE.
    # Read that instead, and derive closing velocity from the distance time-series.
    self._ccnc_lead = self.CP.flags & HyundaiFlags.CCNC and self.CP.carFingerprint == "KIA_CARNIVAL_HEV_4TH_GEN"
    self._ccnc_last_dist = None
    self._ccnc_last_dist_time = None
    self._ccnc_last_vrel = 0.0

  @property
  def use_radar_interface_ext(self) -> bool:
    return self.use_escc or self.CP.flags & (HyundaiFlags.CAMERA_SCC | HyundaiFlags.CANFD_CAMERA_SCC)

  def get_msg_src(self) -> str | None:
    if self.use_escc:
      return "ESCC"
    if self._ccnc_lead:
      return "CCNC_0x162"
    if self.CP.flags & (HyundaiFlags.CAMERA_SCC | HyundaiFlags.CANFD_CAMERA_SCC):
      return "SCC_CONTROL" if self.CP.flags & HyundaiFlags.CANFD_CAMERA_SCC else "SCC11"

  def get_radar_ext_can_parser(self) -> CANParser:
    if self.ESCC.enabled:
      lead_src, bus = "ESCC", 0
    elif self._ccnc_lead:
      lead_src = "CCNC_0x162"
      bus = CanBus(self.CP).CAM
    elif self.CP.flags & (HyundaiFlags.CAMERA_SCC | HyundaiFlags.CANFD_CAMERA_SCC):
      lead_src = "SCC_CONTROL" if self.CP.flags & HyundaiFlags.CANFD_CAMERA_SCC else "SCC11"
      bus = CanBus(self.CP).CAM if self.CP.flags & HyundaiFlags.CANFD_CAMERA_SCC else 2
    else:
      return None

    messages = [(lead_src, 50)]
    return CANParser(DBC[self.CP.carFingerprint][Bus.pt], messages, bus)

  def get_trigger_msg(self, default_trigger_msg) -> int:
    if self.ESCC.enabled:
      return self.ESCC.trigger_msg
    if self._ccnc_lead:
      return 0x162
    if self.CP.flags & (HyundaiFlags.CAMERA_SCC | HyundaiFlags.CANFD_CAMERA_SCC):
      return 0x1A0 if self.CP.flags & HyundaiFlags.CANFD_CAMERA_SCC else 0x420
    return default_trigger_msg

  def initialize_radar_ext(self, default_trigger_msg) -> None:
    if self.ESCC.enabled:
      self.use_escc = True

    self.rcp = self.get_radar_ext_can_parser()
    self.trigger_msg = self.get_trigger_msg(default_trigger_msg)

  def update_ext(self, ret: structs.RadarData) -> structs.RadarData:
    if not self.rcp.can_valid:
      ret.errors.canError = True
      return ret

    for ii in range(1):
      msg_src = self.get_msg_src()
      msg = self.rcp.vl[msg_src]

      if ii not in self.pts:
        self.pts[ii] = structs.RadarData.RadarPoint()
        self.pts[ii].trackId = self.track_id
        self.track_id += 1

      if self._ccnc_lead:
        # Carnival HEV: lead range is CCNC_0x162.LEAD_DISTANCE (0.1 m). "LEAD"
        # is the display state (0=hidden, 1=gray, 2=white...); 2 => a confirmed
        # lead. Closing velocity is derived from the distance time-series (the
        # message carries no explicit velocity field).
        lead_state = msg['LEAD']
        dist = msg['LEAD_DISTANCE']
        valid = lead_state in (1, 2) and 0 < dist < 204.0

        now = time.monotonic()
        if valid:
          if self._ccnc_last_dist is not None and self._ccnc_last_dist_time is not None:
            dt = now - self._ccnc_last_dist_time
            if dt > 0.02:
              vrel = (dist - self._ccnc_last_dist) / dt
              # lightweight smoothing to avoid 0.1m quantization noise
              self._ccnc_last_vrel = 0.7 * self._ccnc_last_vrel + 0.3 * vrel
          self._ccnc_last_dist = dist
          self._ccnc_last_dist_time = now

          self.pts[ii].measured = True
          self.pts[ii].dRel = dist
          self.pts[ii].yRel = float('nan')
          self.pts[ii].vRel = self._ccnc_last_vrel
          self.pts[ii].aRel = float('nan')
          self.pts[ii].yvRel = float('nan')
        else:
          self._ccnc_last_dist = None
          self._ccnc_last_dist_time = None
          self._ccnc_last_vrel = 0.0
          del self.pts[ii]
        continue

      valid = msg['ACC_ObjDist'] < 204.6 if self.CP.flags & HyundaiFlags.CANFD_CAMERA_SCC else msg['ACC_ObjStatus']
      if valid:
        self.pts[ii].measured = True
        self.pts[ii].dRel = msg['ACC_ObjDist']
        self.pts[ii].yRel = float('nan')  # FIXME-SP: Only some cars have lateral position from SCC
        self.pts[ii].vRel = msg['ACC_ObjRelSpd']
        self.pts[ii].aRel = float('nan')  # TODO-SP: calculate from ACC_ObjRelSpd and with timestep 50Hz (needs to modify in interfaces.py)
        self.pts[ii].yvRel = float('nan')

      else:
        del self.pts[ii]

    ret.points = list(self.pts.values())
    return ret
