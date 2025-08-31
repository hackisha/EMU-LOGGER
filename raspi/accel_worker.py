from typing import Callable, Dict, Any, Optional
from time import sleep
try:
    from smbus2 import SMBus
except ImportError:
    SMBus = None

# ADXL345 레지스터
REG_DEVID       = 0x00
REG_POWER_CTL   = 0x2D
REG_DATA_FORMAT = 0x31
REG_BW_RATE     = 0x2C
REG_DATAX0      = 0x32

ADXL345_ADDR = 0x53

class AccelWorker:
    def __init__(
        self,
        i2c_bus: int = 1,
        address: int = ADXL345_ADDR,
        on_update: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        self.i2c_bus_num = i2c_bus
        self.addr = address
        self.on_update = on_update
        self.bus: Optional[SMBus] = None
        self.enabled = SMBus is not None

    def start(self):
        if not self.enabled:
            raise RuntimeError("smbus2 가 설치되어 있지 않습니다. pip3 install smbus2")
        self.bus = SMBus(self.i2c_bus_num)
        try:
            devid = self.bus.read_byte_data(self.addr, REG_DEVID)
        except Exception as e:
            raise RuntimeError(f"ADXL345 접근 실패: {e}")

        # 설정 (기존과 동일)
        self.bus.write_byte_data(self.addr, REG_BW_RATE, 0x0A)
        self.bus.write_byte_data(self.addr, REG_DATA_FORMAT, 0x08)
        self.bus.write_byte_data(self.addr, REG_POWER_CTL, 0x08)
        sleep(0.02)

    def read_once(self):
        """한 번 읽어 g 단위로 변환하고 콜백을 호출합니다."""
        if not self.bus:
            return
        try:
            data = self.bus.read_i2c_block_data(self.addr, REG_DATAX0, 6)

            y = self._to_int16(data[1] << 8 | data[0])
            x = self._to_int16(data[3] << 8 | data[2])
            z = -(self._to_int16(data[5] << 8 | data[4]))

            lsb_g = 0.0156
            ax_g = x * lsb_g
            ay_g = y * lsb_g
            az_g = z * lsb_g

            out = {"ax_g": ax_g, "ay_g": ay_g, "az_g": az_g}

            # 콜백이 있으면 호출 (이 데이터를 main.py로 전달)
            if self.on_update:
                self.on_update(out)

        except Exception:
            # 센서 오류는 무시
            return

    @staticmethod
    def _to_int16(v: int) -> int:
        return v - 65536 if v & 0x8000 else v

    def shutdown(self):
        if self.bus:
            try:
                self.bus.close()
            except Exception:
                pass
            self.bus = None
