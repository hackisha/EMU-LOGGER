import serial
import pynmea2
import time
from typing import Callable, Dict, Any, Optional

class GpsWorker:
    # 시리얼 포트에서 NMEA 문장을 읽고 파싱하여 GPS 데이터를 콜백으로 전달
    def __init__(
        self,
        port: str,
        baudrate: int,
        on_update: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.port = port
        self.baudrate = baudrate
        self.on_update = on_update
        self.ser: Optional[serial.Serial] = None
        self.is_valid = False

    def start(self):
        """시리얼 포트를 엽니다."""
        try:
            self.ser = serial.Serial(self.port, baudrate=self.baudrate, timeout=0.1)
            print(f"GPS 포트({self.port}) 열기 성공.")
        except serial.SerialException as e:
            print(f"경고: GPS 포트({self.port})를 열 수 없습니다: {e}")
            self.ser = None

    def read_once(self):
        """
        시리얼 버퍼에서 한 줄을 읽어 NMEA 문장을 파싱합니다.
        유효한 데이터가 있으면 콜백을 호출합니다.
        """
        if not self.ser or not self.ser.is_open:
            return

        try:
            line = self.ser.readline().decode("utf-8", errors="ignore")
            if not line:
                return

            msg = pynmea2.parse(line)
            parsed_data: Dict[str, Any] = {}

            if isinstance(msg, pynmea2.types.talker.RMC) and msg.status == 'A':
                self.is_valid = True
                parsed_data.update({
                    "lat": msg.latitude,
                    "lon": msg.longitude,
                    "GPS_Speed_KPH": msg.spd_over_grnd * 1.852 if msg.spd_over_grnd is not None else 0.0,
                    "heading": msg.true_course if msg.true_course is not None else None,
                })

            elif isinstance(msg, pynmea2.types.talker.GGA):
                self.is_valid = msg.gps_qual > 0
                parsed_data.update({
                    "satellites": int(msg.num_sats or 0),
                    "altitude": msg.altitude,
                    "gps_fix": self.is_valid,
                })

            if self.on_update and parsed_data:
                self.on_update(parsed_data)

        except (pynmea2.ParseError, UnicodeDecodeError, ValueError):
            # 파싱, 디코딩, 값 변환 오류는 무시하고 계속 진행
            return
        except serial.SerialException:
            print("GPS 시리얼 에러. 포트를 닫습니다.")
            self.shutdown()


    def shutdown(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("GPS 포트 종료.")
            self.ser = None
