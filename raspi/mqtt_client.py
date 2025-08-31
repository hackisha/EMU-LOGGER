import paho.mqtt.client as mqtt
import json

class MqttClient:
    """MQTT 통신을 관리하는 클라이언트 클래스"""
    def __init__(self, broker_address="localhost", port=1883):
        self.broker_address = broker_address
        self.port = port
        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("[INFO] MQTT 브로커에 연결되었습니다.")
        else:
            print(f"[ERROR] MQTT 연결 실패 (Code: {rc})")

    def _on_disconnect(self, client, userdata, rc):
        print("[INFO] MQTT 브로커와의 연결이 끊어졌습니다.")

    def connect(self):
        """브로커에 연결을 시도합니다."""
        try:
            self.client.connect(self.broker_address, self.port, 60)
            self.client.loop_start()  # 백그라운드 스레드에서 네트워크 루프 시작
        except Exception as e:
            print(f"[ERROR] MQTT 브로커에 연결할 수 없습니다: {e}")

    def publish(self, topic, payload):
        """지정된 토픽으로 데이터를 발행합니다."""
        if not self.client.is_connected():
            # print("[WARNING] MQTT가 연결되지 않아 데이터를 발행할 수 없습니다.")
            return

        if isinstance(payload, dict):
            payload = json.dumps(payload) # dict를 JSON 문자열로 변환

        self.client.publish(topic, payload)

    def disconnect(self):
        """브로커와의 연결을 종료합니다."""
        self.client.loop_stop()
        self.client.disconnect()
