# EMU LOGGER

> Raspberry Pi에서 차량 ECU의 CAN 텔레메트리, GPS, 가속도 데이터를 수집해 CSV로 기록하고 MQTT와 웹 대시보드로 전달하는 모터스포츠 데이터 로거입니다.

이 저장소는 EMU BLACK ECU를 사용하는 차량을 대상으로 한 데이터 로거 프로토타입입니다. 수집기에는 Linux SocketCAN, NMEA GPS, ADXL345 계열 가속도 센서, GPIO 버튼·상태 LED 제어가 구현되어 있으며, 서버는 MQTT 메시지를 Flask-SocketIO 대시보드로 중계합니다. 아래 설명은 현재 저장소에 추적된 소스와 설정만을 기준으로 합니다.

## 핵심 기능

- **차량 CAN / SocketCAN**: `can0`를 1 Mbps로 올리고 EMU 프레임 `0x600`~`0x607` 및 사용자 프레임 `0x500`을 파싱합니다. RPM, 스로틀, 흡기·냉각수·오일 온도, 압력, 람다, 기어, 배터리 전압 등으로 변환합니다.
- **GPS**: `/dev/serial0`, 9,600 baud에서 NMEA RMC/GGA 문장을 읽어 위치, 속도, 방위, 고도, 위성 수와 fix 상태를 만들도록 작성되어 있습니다.
- **가속도**: I²C의 ADXL345에서 X/Y/Z 축 값을 읽고 g 단위로 변환합니다. CSV 스키마에는 자이로 필드도 있지만 현재 worker가 실제로 갱신하는 값은 `ax_g`, `ay_g`, `az_g`입니다.
- **CSV 로깅**: 실행 시 `/home/pi/logs/datalog_YYYYMMDD_HHMMSS.csv`를 만들며 약 20 Hz 주기로 최신 CAN/GPS/가속도 스냅샷을 기록합니다. GPIO 버튼으로 기록을 토글하고 LED로 상태를 표시합니다.
- **MQTT 텔레메트리**: 수집 데이터를 `car/emu/telemetry`에 JSON으로 약 5 Hz 발행하도록 설정되어 있습니다.
- **웹 모니터링**: Flask 서버가 같은 MQTT 토픽을 구독하고 `telemetry_update` Socket.IO 이벤트로 브라우저에 전달합니다. 대시보드는 GPS, 가속도, 차량 센서 화면을 제공합니다.

## 데이터 흐름

```mermaid
flowchart LR
    ECU[EMU BLACK ECU] -->|CAN 1 Mbps| SC[SocketCAN can0]
    GPS[GPS 수신기] -->|NMEA /dev/serial0| COL[raspi 수집기]
    ACC[ADXL345] -->|I2C| COL
    SC --> COL
    BTN[GPIO 버튼] --> COL
    COL -->|약 20 Hz| CSV[/home/pi/logs/*.csv]
    COL -->|JSON, 약 5 Hz| MQTT[MQTT broker<br/>car/emu/telemetry]
    MQTT --> WEB[Flask + Flask-SocketIO]
    WEB -->|telemetry_update| UI[브라우저 대시보드]
```

수집 JSON의 최상위 구조는 `timestamp`, `can`, `gps`, `accel`입니다. 웹 서버는 마지막 텔레메트리를 보관해 새 Socket.IO 연결에도 전달하며, `/api/submit`으로 받은 JSON도 동일한 화면 이벤트로 중계합니다.

## 코드 지도

| 영역 | 실제 모듈 | 역할 |
| --- | --- | --- |
| 수집 오케스트레이션 | [`raspi/main.py`](raspi/main.py) | worker 수명주기, CSV, MQTT, GPIO 제어 |
| CAN | [`raspi/can_worker.py`](raspi/can_worker.py) | SocketCAN 초기화, EMU/사용자 프레임 파싱, CAN 송신 |
| GPS | [`raspi/gps_worker.py`](raspi/gps_worker.py) | NMEA RMC/GGA 파싱을 의도한 worker |
| 가속도 | [`raspi/accel_worker.py`](raspi/accel_worker.py) | ADXL345 초기화 및 3축 가속도 변환 |
| GPIO | [`raspi/gpio_ctl.py`](raspi/gpio_ctl.py) | 버튼, 로깅·오류·Wi-Fi LED |
| MQTT 클라이언트 | [`raspi/mqtt_client.py`](raspi/mqtt_client.py) | 수집기 측 연결과 발행 |
| 수집 설정 | [`raspi/config.py`](raspi/config.py) | 장치, 경로, 핀, MQTT 설정 |
| 웹 서버 | [`web_server/telemetry_server.py`](web_server/telemetry_server.py) | MQTT 구독, HTTP, Socket.IO 중계 |
| 웹 설정 | [`web_server/config.py`](web_server/config.py) | 서버 측 MQTT 토픽과 broker 설정 |
| 대시보드 | [`web_server/dashboard/`](web_server/dashboard/) | 차량 센서, GPS, 가속도 화면 |
| 하드웨어 자료 | [`PCB/README.md`](PCB/README.md) | PCB 자료 안내 |
| 랩 타이머 | [`laptimer/lapTimer.ino`](laptimer/lapTimer.ino) | Arduino 랩 타이머 코드 |

## 하드웨어 및 런타임 전제

- Raspberry Pi 또는 Linux SocketCAN과 GPIO/I²C/UART를 제공하는 환경
- `can0` CAN 인터페이스와 EMU BLACK ECU 연결
- `/dev/serial0`에 연결된 9,600 baud NMEA GPS
- I²C 버스 1, 주소 `0x53`의 ADXL345
- BCM GPIO 17(버튼), 27(로깅 LED), 22(오류 LED), 5(Wi-Fi LED)
- Python 3 및 `python-can`, `pyserial`, `pynmea2`, `paho-mqtt`, `RPi.GPIO`, `smbus` 계열 패키지

웹 서버에 필요한 추적 의존성 목록은 [`web_server/requirements.txt`](web_server/requirements.txt)에 있습니다. 반면 **저장소 루트 또는 `raspi/`에는 수집기용 `requirements.txt`가 없습니다.** 따라서 현재 트리만으로 수집기 의존성을 일괄 설치하는 명령은 제공할 수 없습니다.

## 설치 및 실행 상태

### 웹 서버

웹 서버 부분은 추적된 의존성 파일을 기준으로 다음과 같이 준비할 수 있습니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r web_server/requirements.txt
python3 web_server/telemetry_server.py
```

기본 바인딩은 `0.0.0.0:5000`입니다. 실행에는 MQTT broker에 대한 네트워크 연결이 필요합니다.

### Raspberry Pi 수집기

패키지 상대 import 구조상 저장소 루트에서 아래 명령으로 실행하는 형태가 의도되어 있습니다.

```bash
sudo python3 -m raspi.main
```

그러나 **현재 체크아웃에서는 end-to-end 실행이 차단됩니다.**

1. [`raspi/main.py`](raspi/main.py)는 `from .wifi_monitor import start_wifi_monitor`를 사용하지만, 추적 트리에는 `raspi/wifi_monitor.py`가 없습니다. 유사 구현은 확장자 없는 [`raspi/wifi_monitor_worker`](raspi/wifi_monitor_worker)에만 있어 import할 수 없습니다.
2. [`raspi/gps_worker.py`](raspi/gps_worker.py)는 파일 앞부분에 메인 수집기 코드가 중복되어 있고 그 안에서 `from .gps_worker import GpsWorker`로 자기 모듈을 다시 import합니다. `GpsWorker` 클래스는 그 뒤에 정의되어 있어 정상적인 모듈 import를 막는 순환 import 문제가 있습니다.

따라서 위 수집기 명령은 현재 상태의 성공 절차가 아니라 의도된 진입점입니다. 이 README 작업에서는 요청 범위에 따라 소스 문제를 수정하지 않았습니다. 또한 현재 트리에는 systemd unit이나 ngrok 설정이 없으므로 자동 시작·외부 터널링 절차를 제공하지 않습니다.

## 검증

문서의 내용은 다음 추적 파일을 대조해 확인했습니다.

- CAN ID, 비트레이트, 파싱 필드: [`raspi/config.py`](raspi/config.py), [`raspi/can_worker.py`](raspi/can_worker.py)
- GPS 장치와 파싱 의도 및 현재 결함: [`raspi/gps_worker.py`](raspi/gps_worker.py)
- 가속도 센서와 출력 필드: [`raspi/accel_worker.py`](raspi/accel_worker.py)
- CSV 경로·주기·스키마와 MQTT 발행: [`raspi/main.py`](raspi/main.py)
- MQTT 구독, Flask 라우팅, Socket.IO 이벤트: [`web_server/telemetry_server.py`](web_server/telemetry_server.py)
- 설치 가능 범위: Git 추적 트리와 [`web_server/requirements.txt`](web_server/requirements.txt)

실차 CAN 버스, GPS, I²C 센서와 Raspberry Pi GPIO가 필요한 하드웨어 통합 검증은 이 저장소만으로 재현할 수 없습니다. 위 두 import/모듈 문제 때문에 수집기 전체 실행 검증도 아직 통과할 수 없습니다.

## 제한사항

- 데이터는 여러 worker가 갱신한 “최신 값”을 합쳐 기록하므로 각 센서 샘플이 정확히 같은 시각에 취득됐다고 보장하지 않습니다.
- CSV는 메모리의 마지막 값을 반복 기록할 수 있으며, 센서별 신선도나 누락 여부를 별도 표시하지 않습니다.
- MQTT는 연결되지 않으면 발행을 건너뛰며, 로컬 재전송 큐나 영속 버퍼가 없습니다.
- 웹 서버는 마지막 메시지 하나만 메모리에 보관합니다. 재시작하면 이 상태는 사라집니다.
- 현재 코드에는 자동화 테스트와 CI 설정이 추적되어 있지 않습니다.
- 일부 소스 주석과 문자열은 문자 인코딩이 깨진 상태입니다.

## 보안 주의사항

현재 수집기와 웹 서버의 기본 broker는 [`test.mosquitto.org:1883`](raspi/config.py)입니다. 이 포트는 코드상 사용자 인증과 TLS 암호화를 사용하지 않는 **공개 개발용 설정**입니다. 차량 위치와 주행 데이터가 제3자에게 노출되거나, 동일 토픽을 아는 사용자가 데이터를 주입·구독할 수 있으므로 실제 차량, 시연 행사, 운영 환경에 그대로 사용하면 안 됩니다.

운영 환경에서는 다음 조치가 필요합니다.

- 관리하는 전용 broker로 교체하고 TLS 포트와 서버 인증서 검증 사용
- 계정 인증과 토픽별 ACL 적용, 차량별 추측하기 어려운 토픽 분리
- 수집기와 웹 서버의 자격 증명을 소스 밖의 환경 변수 또는 권한이 제한된 secret 저장소에서 주입
- Flask 서버를 인터넷에 직접 노출하지 않고 인증·접근 제어가 있는 역방향 프록시 뒤에 배치
- `/api/submit`에 인증, 요청 크기 제한, 입력 스키마 검증 추가
- MQTT 명령 토픽이 CAN 송신으로 이어질 수 있으므로 명령 채널을 텔레메트리보다 더 엄격하게 격리

## 현재 저장소 구조

```text
EMU-LOGGER/
├── PCB/                    # 회로도, PCB JSON, Gerber 및 안내
├── laptimer/               # Arduino 랩 타이머
├── raspi/                  # 차량 데이터 수집기와 하드웨어 worker
│   ├── main.py
│   ├── can_worker.py
│   ├── gps_worker.py
│   ├── accel_worker.py
│   ├── gpio_ctl.py
│   ├── mqtt_client.py
│   └── config.py
├── web_server/             # Flask-Socket.IO 서버와 대시보드
│   ├── telemetry_server.py
│   ├── config.py
│   ├── requirements.txt
│   ├── dashboard/
│   └── static/
└── README.md
```

이 구조는 주요 추적 항목을 요약한 것이며, `raspi/`에는 실험용 DRS·버튼 진입점도 함께 남아 있습니다.
