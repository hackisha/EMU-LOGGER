# main.py (데이터 송신 전용, ADXL345 사용, 모든 기능 포함, 자동 로깅 시작)

import os
import sys
import csv
import signal
import time
import threading
from datetime import datetime
import json
import struct

# 상대 경로 임포트를 유지합니다 (패키지 실행 방식)
from .config import (
    LOG_DIR, SERIAL_PORT, BAUD_RATE,
    MQTT_BROKER, MQTT_PORT, MQTT_TOPICS, MQTT_UPLOAD_INTERVAL_SEC
)
from .mqtt_client import MqttClient
from .gpio_ctl import GpioController
from .can_worker import CanWorker
from .gps_worker import GpsWorker
from .wifi_monitor import start_wifi_monitor
from .accel_worker import AccelWorker

# ======== 전역 변수 ========
exit_event = threading.Event()
logging_active = False
last_button_press_time = 0.0
last_sent_lap = 0

# 데이터 저장소
latest_can_data = {}
latest_gps_data = {}
latest_acc_data = {}

# CSV 로깅 관련
csv_file = None
csv_writer = None

# ======== 콜백 함수들 ========
def on_can_message(arbitration_id: int, parsed: dict):
    global latest_can_data
    latest_can_data.update(parsed)

def on_gps_update(parsed: dict):
    global latest_gps_data
    latest_gps_data.update(parsed)

def on_accel_update(parsed: dict):
    global latest_acc_data
    latest_acc_data.update(parsed)

# ======== 핵심 로직 ========
def toggle_logging_state(gpio: GpioController):
    global logging_active, csv_file, csv_writer
    logging_active = not logging_active
    if logging_active:
        gpio.set_logging_led(True)
        os.makedirs(LOG_DIR, exist_ok=True)
        filename = f"{LOG_DIR}/datalog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        print(f"\n[INFO] 로깅 시작 -> {filename}")
        csv_file = open(filename, 'w', newline='', encoding='utf-8')
        fieldnames = [
            "Timestamp", "Latitude", "Longitude", "GPS_Speed_KPH", "Satellites", "Altitude_m", "Heading_deg",
            "RPM","TPS_percent","IAT_C","MAP_kPa","PulseWidth_ms","AnalogIn1_V","AnalogIn2_V","AnalogIn3_V","AnalogIn4_V",
            "VSS_kmh","Baro_kPa","OilTemp_C","OilPressure_bar","FuelPressure_bar","CLT_C","EOT_OUT", "fuelPumpTemp","IgnAngle_deg","DwellTime_ms",
            "WBO_Lambda","LambdaCorrection_percent","EGT1_C","EGT2_C","Gear","EmuTemp_C","Batt_V","CEL_Error","Flags1",
            "Ethanol_percent","DBW_Pos_percent","DBW_Target_percent","TC_drpm_raw","TC_drpm","TC_TorqueReduction_percent",
            "PitLimit_TorqueReduction_percent","AnalogIn5_V","AnalogIn6_V","OutFlags1","OutFlags2","OutFlags3","OutFlags4",
            "BoostTarget_kPa","PWM1_DC_percent","DSG_Mode","LambdaTarget","PWM2_DC_percent","FuelUsed_L",
            "ax_g", "ay_g", "az_g", "gx_dps", "gy_dps", "gz_dps"
        ]
        csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction='ignore')
        csv_writer.writeheader()
    else:
        print("\n[INFO] 로깅 중지.")
        gpio.set_logging_led(False)
        if csv_file:
            name = csv_file.name
            csv_file.close()
            print(f"[INFO] 로그 파일 저장 완료: {name}")
        csv_file = None
        csv_writer = None

def write_csv_log_entry(gpio: GpioController):
    if not logging_active or not csv_writer:
        return
    full_row = { "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")}
    full_row.update(latest_gps_data)
    full_row.update(latest_can_data)
    full_row.update(latest_acc_data)
    csv_writer.writerow(full_row)
    gpio.blink_logging_led_once()

def print_status_line():
    global last_sent_lap
    gps_status = "OK" if latest_gps_data.get("gps_fix") else "No Fix"
    rpm = latest_can_data.get('RPM', 0)
    vss = latest_can_data.get('VSS_kmh', 0.0)
    logging_status = "ON" if logging_active else "OFF"
    status_text = (
        f"RPM:{rpm:>5} | VSS:{vss:>5.1f}km/h | GPS:{gps_status} | Logging:{logging_status} | Lap Sent:{last_sent_lap}"
    )
    sys.stdout.write("\r" + status_text + "    ")
    sys.stdout.flush()

def mqtt_uploader(mqtt: MqttClient, stop_event: threading.Event):
    while not stop_event.is_set():
        data_to_publish = {
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            'can': latest_can_data,
            'gps': latest_gps_data,
            'accel': latest_acc_data
        }
        if latest_can_data or latest_gps_data or latest_acc_data:
            mqtt.publish(MQTT_TOPICS["TELEMETRY"], json.dumps(data_to_publish))
        stop_event.wait(MQTT_UPLOAD_INTERVAL_SEC)

def handle_exit(signum, frame):
    print("\n[INFO] 종료 신호 수신. 리소스를 정리합니다...")
    exit_event.set()

def worker_loop(worker, stop_event: threading.Event):
    method_name = "recv_once" if hasattr(worker, "recv_once") else "read_once"
    read_method = getattr(worker, method_name)
    while not stop_event.is_set():
        try:
            read_method()
        except Exception as e:
            print(f"\n[ERROR] {type(worker).__name__} 스레드에서 오류 발생: {e}", file=sys.stderr)
            if isinstance(e, (IOError, OSError)):
                break
        time.sleep(0.001)

def main():
    """메인 실행 함수"""
    global last_button_press_time, last_sent_lap

    if os.geteuid() != 0:
        print("오류: 이 스크립트는 sudo 권한으로 실행해야 합니다.")
        sys.exit(1)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    # --- 초기화 ---
    gpio = GpioController()
    mqtt_client = MqttClient(broker_address=MQTT_BROKER, port=MQTT_PORT)
    can_worker = CanWorker(on_message=on_can_message)
    gps_worker = GpsWorker(port=SERIAL_PORT, baudrate=BAUD_RATE, on_update=on_gps_update)
    accel_worker = AccelWorker(on_update=on_accel_update)

    # --- main 함수 내부에 관련 함수들을 정의하여 can_worker에 쉽게 접근 ---
    def send_lap_to_adu(lap: int):
        global last_sent_lap
        try:
            payload = struct.pack('<B', lap)
            full_payload = payload.ljust(8, b'\x00')
            can_worker.send_message(0x700, full_payload)
            last_sent_lap = lap
        except Exception as e:
            print(f"[main] ADU로 랩 카운트 전송 실패: {e}")

    def on_mqtt_message(client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        command_topic = MQTT_TOPICS.get("COMMAND_LAP", "vehicle/command/lap")
        if topic == command_topic:
            try:
                data = json.loads(payload)
                lap_count = data.get("lap_count")
                if lap_count is not None:
                    print(f"\n[MQTT] 랩 카운트 수신: {lap_count}. ADU로 CAN 메시지를 전송합니다.")
                    send_lap_to_adu(lap_count)
            except Exception as e:
                print(f"\n[MQTT] 랩 카운트 메시지 처리 오류: {e}")

    # MQTT 클라이언트 콜백 및 구독 설정
    mqtt_client.client.on_message = on_mqtt_message
    mqtt_client.connect()
    command_topic = MQTT_TOPICS.get("COMMAND_LAP", "vehicle/command/lap")
    mqtt_client.client.subscribe(command_topic)
    print(f"[MQTT] 랩 카운트 명령 구독 시작. Topic: {command_topic}")

    # --- Worker 시작 ---
    try:
        can_worker.start()
        gps_worker.start()
        accel_worker.start()
    except Exception as e:
        print(f"[ERROR] Worker 시작 실패: {e}", file=sys.stderr)
        gpio.set_error_led(True)
        exit_event.set()
        return

    # --- 스레드 생성 ---
    wifi_monitor_thread = threading.Thread(target=start_wifi_monitor, args=(gpio, exit_event), daemon=True)
    mqtt_thread = threading.Thread(target=mqtt_uploader, args=(mqtt_client, exit_event), daemon=True)
    can_thread = threading.Thread(target=worker_loop, args=(can_worker, exit_event), daemon=True)
    gps_thread = threading.Thread(target=worker_loop, args=(gps_worker, exit_event), daemon=True)
    accel_thread = threading.Thread(target=worker_loop, args=(accel_worker, exit_event), daemon=True)

    # --- 스레드 시작 ---
    wifi_monitor_thread.start()
    mqtt_thread.start()
    print(f"MQTT 업로드 스레드 시작 (Interval: {MQTT_UPLOAD_INTERVAL_SEC}s)")
    can_thread.start()
    gps_thread.start()
    accel_thread.start()
    print("데이터 수집 스레드 시작 (CAN, GPS, ACCEL)")

    # --- 스크립트 실행 시 로깅 자동 시작 ---
    print("\n[INFO] 데이터 로깅을 자동으로 시작합니다.")
    toggle_logging_state(gpio)

    if not exit_event.is_set():
        print("\n[INFO] 데이터 수집이 시작되었습니다. 버튼을 눌러 로깅을 중지/재시작할 수 있습니다. (종료: Ctrl+C)")

    # --- 메인 루프 ---
    last_csv_write_time = 0.0
    try:
        while not exit_event.is_set():
            now = time.time()
            if gpio.read_button_pressed() and (now - last_button_press_time > 0.3):
                last_button_press_time = now
                toggle_logging_state(gpio)
            if logging_active and (now - last_csv_write_time > 0.05):
                write_csv_log_entry(gpio)
                last_csv_write_time = now
            print_status_line()
            time.sleep(0.05)
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        print(f"\n[FATAL] 메인 루프에서 심각한 오류 발생: {e}", file=sys.stderr)
        gpio.set_error_led(True)
    finally:
        exit_event.set()
        print("\n[INFO] 모든 스레드와 Worker를 종료합니다.")
        can_thread.join(timeout=0.5)
        gps_thread.join(timeout=0.5)
        accel_thread.join(timeout=0.5)
        mqtt_thread.join(timeout=0.5)
        can_worker.shutdown()
        gps_worker.shutdown()
        accel_worker.shutdown()
        mqtt_client.disconnect()
        if csv_file and not csv_file.closed:
            csv_file.close()
            print(f"[INFO] 로그 파일 저장 완료: {csv_file.name}")
        gpio.cleanup()
        print("[INFO] 프로그램이 완전히 종료되었습니다.")

if __name__ == "__main__":
    main()
pi@raspberrypi:~/logger $ ls
accel_worker.py        btn_version_main.py  can_worker.py       config.py  gpio_ctl.py   gps_worker.py  main.py         publisher.py  requirements.txt  telemetry_server.py
b_telemetry_server.py  can_bus_test.py      can_worker_test.py  dashboard  gpio_ctrl.py  __init__.py    mqtt_client.py  __pycache__   static            wifi_monitor.py
pi@raspberrypi:~/logger $ ls
accel_worker.py        btn_version_main.py  can_worker.py       config.py  gpio_ctl.py   gps_worker.py  main.py         publisher.py  requirements.txt  telemetry_server.py
b_telemetry_server.py  can_bus_test.py      can_worker_test.py  dashboard  gpio_ctrl.py  __init__.py    mqtt_client.py  __pycache__   static            wifi_monitor.py
pi@raspberrypi:~/logger $ cat gps_worker.py
import serial
import pynmea2
import time
from typing import Callable, Dict, Any, Optional

class GpsWorker:
    def __init__(
        self,
        port: str,
        baudrate: int,
        on_update: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.port = port
        self.baudrate = baudrate # config.py에서 설정된 9600 값을 사용
        self.on_update = on_update
        self.ser: Optional[serial.Serial] = None
        self.temp_gps_data: Dict[str, Any] = {}

    def start(self):
        """
        GPS 모듈에 9600bps로 연결하고, 10Hz 업데이트 주기로 설정합니다.
        """
        try:
            # 1. 설정된 9600 보드레이트로 포트를 엽니다.
            self.ser = serial.Serial(self.port, baudrate=self.baudrate, timeout=0.2)
            print(f"GPS 포트({self.port})에 {self.baudrate}bps로 연결 성공.")

            # 2. 10Hz 업데이트 주기 설정 UBX 명령어를 전송합니다.
            set_10hz_command = bytes([
                0xB5, 0x62, # Header
                0x06, 0x08, # Class, ID (CFG-RATE)
                0x06, 0x00, # Length
                0x64, 0x00, # measRate (100ms -> 10Hz)
                0x01, 0x00, # navRate (1)
                0x01, 0x00, # timeRef (GPS Time)
                0x7A, 0x80  # Checksum
            ])
            self.ser.write(set_10hz_command)
            print("GPS 모듈에 10Hz 출력 설정 명령어를 전송했습니다.")
            time.sleep(0.1) # 설정 적용을 위한 짧은 대기

        except serial.SerialException as e:
            print(f"경고: GPS 포트({self.port}) 연결 또는 설정 중 오류 발생: {e}")
            self.ser = None
            return

    def read_once(self):
        """
        시리얼 버퍼에서 데이터를 읽어 NMEA 문장을 파싱하고,
        필수 데이터가 모두 모이면 하나의 패킷으로 조합하여 콜백을 호출합니다.
        """
        if not self.ser or not self.ser.is_open:
            return

        try:
            line = self.ser.readline().decode("utf-8", errors="ignore")
            # 진단 목적으로 RAW 데이터 출력
            if line:
                print(f"[GPS RAW]: {line.strip()}")
            if not line:
                return

            msg = pynmea2.parse(line)

            if isinstance(msg, pynmea2.types.talker.RMC):
                self.temp_gps_data['lat'] = msg.latitude
                self.temp_gps_data['lon'] = msg.longitude
                self.temp_gps_data['GPS_Speed_KPH'] = msg.spd_over_grnd * 1.852 if msg.spd_over_grnd is not None else 0.0
                self.temp_gps_data['heading'] = msg.true_course if msg.true_course is not None else None
                self.temp_gps_data['gps_fix'] = msg.status == 'A'
            elif isinstance(msg, pynmea2.types.talker.GGA):
                self.temp_gps_data['altitude'] = msg.altitude
                self.temp_gps_data['satellites'] = int(msg.num_sats or 0)
                self.temp_gps_data['gps_fix_type'] = msg.gps_qual

            if self.temp_gps_data.get('lat') is not None and self.temp_gps_data.get('GPS_Speed_KPH') is not None:
                if self.on_update:
                    mapped_data = {
                        "Latitude": self.temp_gps_data.get('lat'),
                        "Longitude": self.temp_gps_data.get('lon'),
                        "GPS_Speed_KPH": self.temp_gps_data.get('GPS_Speed_KPH'),
                        "Satellites": self.temp_gps_data.get('satellites'),
                        "Altitude_m": self.temp_gps_data.get('altitude'),
                        "Heading_deg": self.temp_gps_data.get('heading'),
                        "gps_fix": self.temp_gps_data.get('gps_fix'),
                        "gps_fix_type": self.temp_gps_data.get('gps_fix_type')
                    }
                    self.on_update(mapped_data)
                self.temp_gps_data = {}
        except (pynmea2.ParseError, UnicodeDecodeError, ValueError):
            pass
        except serial.SerialException:
            print("GPS 시리얼 에러. 포트를 닫습니다.")
            self.shutdown()

    def shutdown(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("GPS 포트 종료.")
            self.ser = None
