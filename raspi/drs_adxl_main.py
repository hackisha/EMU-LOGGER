# main.py

import os
import sys
import csv
import signal
import time
import threading
from datetime import datetime
import json
import struct

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
last_sent_lap = 0

# DRS 제어용 상태 변수
wing_state = "neutral"  # "up", "down", "neutral"
last_vss = 0.0
accel_start_time = 0
decel_start_time = 0

# 데이터 저장소
latest_can_data = {}
latest_gps_data = {}
latest_acc_data = {}

# CSV 로깅 관련
csv_file = None
csv_writer = None

# ======== main 함수 밖에 위치하는 함수들 ========
def on_gps_update(parsed: dict):
    global latest_gps_data
    latest_gps_data.update(parsed)

def on_accel_update(parsed: dict):
    global latest_acc_data
    latest_acc_data.update(parsed)

def mqtt_uploader(mqtt: MqttClient, stop_event: threading.Event):
    while not stop_event.is_set():
        adu_accel_data = {
            "ax_g": latest_can_data.get("ADU_ax_g"),
            "ay_g": latest_can_data.get("ADU_ay_g"),
            "az_g": latest_can_data.get("ADU_az_g")
        }
        data_to_publish = {
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            'can': latest_can_data,
            'gps': latest_gps_data,
            'accel': latest_acc_data,
            'adu_accel': adu_accel_data
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
    global logging_active, csv_file, csv_writer, last_sent_lap, latest_can_data, latest_gps_data, latest_acc_data
    global gpio, wing_state, last_vss, accel_start_time, decel_start_time

    if os.geteuid() != 0:
        print("오류: 이 스크립트는 sudo 권한으로 실행해야 합니다.")
        sys.exit(1)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    # --- 초기화 ---
    gpio = GpioController()
    mqtt_client = MqttClient(broker_address=MQTT_BROKER, port=MQTT_PORT)
    
    # --- 제어 로직 및 콜백 함수 ---
    def _move_wing_task(direction: bool, duration: float):
        """백그라운드 스레드에서 실행될 윙 이동 작업"""
        gpio.set_motor_direction(direction)
        time.sleep(duration)
        gpio.set_motor_direction(False) # 정지

    def control_drs_wing(speed_kmh: float):
        """차량의 가속/감속 상태에 따라 리어윙을 제어합니다."""
        global last_vss, wing_state, accel_start_time, decel_start_time
        
        speed_delta = speed_kmh - last_vss
        now = time.time()

        DECEL_THRESHOLD = -1.0
        ACCEL_THRESHOLD = 0.5

        try:
            if speed_delta < DECEL_THRESHOLD and wing_state != "up":
                print("\n[DRS] Decelerating -> Wing Up (정방향)")
                wing_thread = threading.Thread(target=_move_wing_task, args=(True, 0.5))
                wing_thread.start()
                wing_state = "up"
            elif speed_delta > ACCEL_THRESHOLD and wing_state != "down":
                print("\n[DRS] Accelerating/Cruising -> Wing Down (역방향)")
                wing_thread = threading.Thread(target=_move_wing_task, args=(False, 0.5))
                wing_thread.start()
                wing_state = "down"
        except Exception as e:
            print(f"\n[ERROR] DRS Wing control failed: {e}")
        
        last_vss = speed_kmh

    def on_can_message(arbitration_id: int, parsed: dict):
        global latest_can_data
        latest_can_data.update(parsed)
        if "VSS_kmh" in parsed:
            control_drs_wing(parsed["VSS_kmh"])

    def toggle_logging_state():
        global logging_active, csv_file, csv_writer
        logging_active = not logging_active
        if logging_active:
            gpio.set_logging_led(True)
            os.makedirs(LOG_DIR, exist_ok=True)
            filename = f"{LOG_DIR}/datalog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            print(f"\n[INFO] 로깅 시작 -> {filename}")
            csv_file = open(filename, 'w', newline='', encoding='utf-8')
            fieldnames = [ "Timestamp", "Latitude", "Longitude", "GPS_Speed_KPH", "Satellites", "Altitude_m", "Heading_deg", "RPM","TPS_percent","IAT_C","MAP_kPa","PulseWidth_ms","AnalogIn1_V","AnalogIn2_V","AnalogIn3_V","AnalogIn4_V", "VSS_kmh","Baro_kPa","OilTemp_C","OilPressure_bar","FuelPressure_bar","CLT_C","EOT_OUT", "fuelPumpTemp","IgnAngle_deg","DwellTime_ms", "WBO_Lambda","LambdaCorrection_percent","EGT1_C","EGT2_C","Gear","EmuTemp_C","Batt_V","CEL_Error","Flags1", "Ethanol_percent","DBW_Pos_percent","DBW_Target_percent","TC_drpm_raw","TC_drpm","TC_TorqueReduction_percent", "PitLimit_TorqueReduction_percent","AnalogIn5_V","AnalogIn6_V","OutFlags1","OutFlags2","OutFlags3","OutFlags4", "BoostTarget_kPa","PWM1_DC_percent","DSG_Mode","LambdaTarget","PWM2_DC_percent","FuelUsed_L", "ax_g", "ay_g", "az_g", "gx_dps", "gy_dps", "gz_dps","ADU_ax_g", "ADU_ay_g", "ADU_az_g" ]
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

    def write_csv_log_entry():
        if not logging_active or not csv_writer: return
        full_row = { "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] }
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
        adu_ax = latest_can_data.get('ADU_ax_g', 0.0)
        adu_ay = latest_can_data.get('ADU_ay_g', 0.0)
        status_text = (
            f"RPM:{rpm:>5} | VSS:{vss:>5.1f}km/h | GPS:{gps_status} | Logging:{logging_status} | Lap Sent:{last_sent_lap} | "
            f"ADU G-Force(X/Y): {adu_ax:+.2f}/{adu_ay:+.2f}"
        )
        sys.stdout.write("\r" + status_text + "    ")
        sys.stdout.flush()
    
    # --- 워커 객체 생성 ---
    can_worker = CanWorker(on_message=on_can_message)
    gps_worker = GpsWorker(port=SERIAL_PORT, baudrate=BAUD_RATE, on_update=on_gps_update)
    accel_worker = AccelWorker(on_update=on_accel_update)
    
    # --- MQTT 관련 로직 ---
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
                    print(f"\n[MQTT] 랩 카운트 수신: {lap_count}")
                    send_lap_to_adu(lap_count)
            except Exception as e:
                print(f"\n[MQTT] 메시지 처리 오류: {e}")
    
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
        
    # --- 리어윙 영점 정렬 ---
    try:
        print("\n[INFO] Rear wing zeroing sequence starting...")
        # 윙을 눕히는 방향(역방향)으로 1초간 작동시켜 강제로 끝까지 보냄
        gpio.set_motor_direction(False)
        time.sleep(1.0)
        gpio.set_motor_direction(False) # 정지
        wing_state = "down" # 초기 상태는 '눕혀짐'
        print("[INFO] Rear wing zeroing sequence finished.")
    except Exception as e:
        print(f"\n[ERROR] Rear wing zeroing failed: {e}")
        
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
    
    # --- 자동 로깅 시작 ---
    toggle_logging_state()
    
    # --- 메인 루프 ---
    last_csv_write_time = 0.0
    last_button_press_time = 0.0
    loop_interval = 0.02
    next_loop_time = time.time()
    try:
        while not exit_event.is_set():
            now = time.time()
            if gpio.read_button_pressed() and (now - last_button_press_time > 0.3):
                last_button_press_time = now
                toggle_logging_state()
            
            if logging_active and (now - last_csv_write_time >= 0.04):
                write_csv_log_entry()
            
            print_status_line()
            
            next_loop_time += loop_interval
            sleep_duration = next_loop_time - time.time()
            if sleep_duration > 0:
                time.sleep(sleep_duration)

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
