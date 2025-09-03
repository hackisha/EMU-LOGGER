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
last_sent_lap = 0 # 마지막으로 ADU에 보낸 랩 카운트 저장

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
    # (기존과 동일)
    pass

def write_csv_log_entry(gpio: GpioController):
    # (기존과 동일)
    pass

def print_status_line():
    """터미널에 현재 상태를 한 줄로 출력합니다."""
    global last_sent_lap
    gps_status = "OK" if latest_gps_data.get("gps_fix") else "No Fix"
    rpm = latest_can_data.get('RPM', 0)
    vss = latest_can_data.get('VSS_kmh', 0.0)
    logging_status = "ON" if logging_active else "OFF"

    #  출력 형식에 Lap Count 추가 
    status_text = (
        f"RPM:{rpm:>5} | VSS:{vss:>5.1f}km/h | GPS:{gps_status} | Logging:{logging_status} | Lap Sent:{last_sent_lap}"
    )
    
    sys.stdout.write("\r" + status_text + "    ")
    sys.stdout.flush()

def mqtt_uploader(mqtt: MqttClient, stop_event: threading.Event):
    # (기존과 동일)
    pass

def handle_exit(signum, frame):
    # (기존과 동일)
    pass

def worker_loop(worker, stop_event: threading.Event):
    # (기존과 동일)
    pass

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
        """랩 카운트를 CAN 메시지로 변환하여 ADU로 전송합니다."""
        try:
            # 8비트 부호없는 정수로 패킹, Little Endian
            payload = struct.pack('<B', lap) 
            full_payload = payload.ljust(8, b'\x00')
            
            # ADU 설정에 맞는 CAN ID (예: 0x700)
            can_worker.send_message(0x700, full_payload)
            last_sent_lap = lap # 마지막으로 보낸 랩 카운트 업데이트
        except Exception as e:
            print(f"[main] ADU로 랩 카운트 전송 실패: {e}")

    def on_mqtt_message(client, userdata, msg):
        """서버로부터 MQTT 메시지를 수신했을 때 호출될 콜백"""
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        
        command_topic = MQTT_TOPICS.get("COMMAND_LAP", "car/command/lap")
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
    mqtt_client.connect() # connect가 loop_start를 호출
    command_topic = MQTT_TOPICS.get("COMMAND_LAP", "car/command/lap")
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

    if not exit_event.is_set():
        print("\n[INFO] 데이터 수집을 시작합니다. 버튼을 눌러 로깅을 제어하세요. (종료: Ctrl+C)")
   # send_lap_to_adu(1) 랩타임 테스트용
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
