from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import paho.mqtt.client as mqtt
import json
from config import MQTT_BROKER, MQTT_PORT, MQTT_TOPICS

# Flask 및 SocketIO 앱 초기화
app = Flask(__name__, template_folder='dashboard', static_folder='static')
socketio = SocketIO(app)

# 마지막으로 수신한 텔레메트리 데이터를 저장할 변수
last_telemetry_data = None

# MQTT 클라이언트 설정
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)

def on_connect(client, userdata, flags, rc):
    """MQTT 브로커 연결 성공 시 토픽 구독"""
    if rc == 0:
        print("[Web Server] MQTT 브로커 연결 성공. 토픽 구독 시작...")
        # 모든 데이터를 받는 메인 토픽을 구독합니다.
        client.subscribe(MQTT_TOPICS["TELEMETRY"])
    else:
        print(f"[Web Server] MQTT 연결 실패 (Code: {rc})")

def on_message(client, userdata, msg):
    """MQTT 메시지 수신 시 데이터 종류를 판별하고 적절한 이벤트를 발생시킴"""
    global last_telemetry_data
    try:
        payload = msg.payload.decode('utf-8')
        data = json.loads(payload)
        
        # 데이터 출처를 확인하여 다른 이벤트 이름으로 전송합니다.
        if data.get("source") and "ArduinoLapTimer" in data.get("source"):
            # 출처가 아두이노 랩타이머인 경우, 'lap_time_update' 이벤트로 전송
            print(f"[MQTT] 아두이노 랩타임 데이터 수신: {data}")
            socketio.emit('lap_time_update', data)
        else:
            # 그 외의 모든 데이터는 'telemetry_update' 이벤트로 전송
            last_telemetry_data = data
            socketio.emit('telemetry_update', data)
            
    except Exception as e:
        print(f"[Web Server] 메시지 처리 오류: {e}")

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

@socketio.on('connect')
def handle_connect():
    """새로운 클라이언트가 접속했을 때 마지막 텔레메트리 데이터를 전송"""
    print("[Web Server] 새로운 클라이언트가 접속했습니다.")
    if last_telemetry_data:
        print("[Web Server] 마지막 텔레메트리 데이터를 새 클라이언트에게 전송합니다.")
        emit('telemetry_update', last_telemetry_data)

@app.route('/api/submit', methods=['POST'])
def handle_external_data():
    """(기존 기능 유지) 외부 HTTP POST 요청을 처리"""
    if not request.is_json:
        return {"status": "error", "message": "Invalid JSON"}, 400

    data = request.get_json()
    print(f"[API] 외부로부터 데이터 수신: {data}")
    # 수신된 데이터를 on_message와 동일한 로직으로 분류
    if data.get("source") and "ArduinoLapTimer" in data.get("source"):
        socketio.emit('lap_time_update', data)
    else:
        global last_telemetry_data
        last_telemetry_data = data
        socketio.emit('telemetry_update', data)
    return {"status": "success"}, 200

@app.route('/')
def index():
    """메인 페이지 렌더링"""
    return render_template('index.html')

@app.route('/<string:page_name>')
def show_page(page_name):
    """다른 HTML 렌더링"""
    try:
        return render_template(page_name)
    except Exception:
        return "Page not found", 404

def run_server():
    """웹 서버와 MQTT 클라이언트를 실행"""
    print("[Web Server] MQTT 클라이언트 시작 중...")
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        print("[Web Server] Flask 서버 시작 중...")
        socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
    except Exception as e:
        print(f"[Web Server] 서버 시작 오류: {e}")
    finally:
        mqtt_client.loop_stop()

if __name__ == '__main__':
    run_server()