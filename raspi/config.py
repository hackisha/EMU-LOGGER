import os

# ===================== 공통 =====================
LOG_DIR = "/home/pi/logs/"
os.makedirs(LOG_DIR, exist_ok=True)

# ===================== CAN =====================
CAN_CHANNEL = "can0"
CAN_BITRATE = 1_000_000
EMU_ID_BASE = 0x600
EMU_IDS = {f"FRAME_{i}": EMU_ID_BASE + i for i in range(8)}

# ===================== GPS =====================
SERIAL_PORT = "/dev/serial0"
BAUD_RATE = 9600

# ===================== GPIO (BCM) =================
BUTTON_PIN = 17
LOGGING_LED_PIN = 27
ERROR_LED_PIN = 22
WIFI_LED_PIN = 5

# ===================== MQTT =====================
MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
MQTT_ENABLE = True
MQTT_UPLOAD_INTERVAL_SEC = 0.2 # 0.2초 (5Hz) 간격으로 데이터 발행
# MQTT 토픽 정의
# 각 데이터 소스별로 토픽을 분리하여 수신 측에서 유연하게 처리하도록 함
TOPIC_PREFIX = "car/emu"
MQTT_TOPICS = {
    "CAN": f"{TOPIC_PREFIX}/can",
    "GPS": f"{TOPIC_PREFIX}/gps",
    "ACCEL": f"{TOPIC_PREFIX}/accel",
    "STATUS": f"{TOPIC_PREFIX}/status",
    "TELEMETRY": f"{TOPIC_PREFIX}/telemetry" # 통합 데이터를 보낼 토픽
}
