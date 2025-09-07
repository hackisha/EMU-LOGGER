# gps_worker.py

import serial
import pynmea2
from typing import Callable, Dict, Any, Optional

class GpsWorker:
    """
    시리얼 포트에서 NMEA 문장을 읽고, 여러 문장을 조합하여
    하나의 완전한 GPS 데이터 패킷을 콜백으로 전달합니다.
    """
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
        
        # 수신된 GPS 데이터 조각을 임시로 저장할 변수 추가
        self.temp_gps_data: Dict[str, Any] = {}

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
        시리얼 버퍼에서 데이터를 읽어 NMEA 문장을 파싱하고,
        필수 데이터가 모두 모이면 하나의 패킷으로 조합하여 콜백을 호출합니다.
        """
        if not self.ser or not self.ser.is_open:
            return

        try:
            line = self.ser.readline().decode("utf-8", errors="ignore")
            if not line:
                return

            msg = pynmea2.parse(line)

            # RMC 문장에서 위도, 경도, 속도, 방향 데이터 추출
            if isinstance(msg, pynmea2.types.talker.RMC):
                self.temp_gps_data['lat'] = msg.latitude
                self.temp_gps_data['lon'] = msg.longitude
                # Knot 단위를 km/h로 변환
                self.temp_gps_data['GPS_Speed_KPH'] = msg.spd_over_grnd * 1.852 if msg.spd_over_grnd is not None else 0.0
                self.temp_gps_data['heading'] = msg.true_course if msg.true_course is not None else None
                # 데이터 유효성(Status 'A') 확인
                self.temp_gps_data['gps_fix'] = msg.status == 'A'

            # GGA 문장에서 고도, 위성 수, Fix 타입 데이터 추출
            elif isinstance(msg, pynmea2.types.talker.GGA):
                self.temp_gps_data['altitude'] = msg.altitude
                self.temp_gps_data['satellites'] = int(msg.num_sats or 0)
                self.temp_gps_data['gps_fix_type'] = msg.gps_qual
            
            # 위도와 속도가 모두 수집되었는지 확인
            if self.temp_gps_data.get('lat') is not None and self.temp_gps_data.get('GPS_Speed_KPH') is not None:
                if self.on_update:
                    # 모든 데이터를 복사하여 콜백으로 전달
                    self.on_update(self.temp_gps_data.copy())
                
                # 다음 패킷을 위해 임시 데이터 초기화
                self.temp_gps_data = {}

        except (pynmea2.ParseError, UnicodeDecodeError, ValueError):
            # 파싱 오류 등은 무시하고 계속 진행
            pass
        except serial.SerialException:
            print("GPS 시리얼 에러. 포트를 닫습니다.")
            self.shutdown()

    def shutdown(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("GPS 포트 종료.")
            self.ser = None
