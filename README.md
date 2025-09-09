# Real-time EMU-BLACK Data Logger
## 프로젝트 소개

순천향대학교 자작자동차 동아리 **무한질주** MF-25 차량의 데이터를 로깅하기위한 프로젝트입니다.
<img width="1404" height="1872" alt="image" src="https://github.com/user-attachments/assets/0eb820fa-982d-4bd3-a8e7-f82300c01d41" />
![KakaoTalk_20250830_125350162_01](https://github.com/user-attachments/assets/f7ca9995-968d-45d5-be5e-0d802b785156)


라즈베리파이를 이용하여 차량의 ECU(EMU BLACK)으로부터 CAN메시지를 로깅하고 GPS, ADXL345 센서를 활용하여 차량의 데이터를 실시간으로 수집하여 MQTT를 통해 원격 웹 대시보드에 시각화하는 프로젝트입니다.
<img width="1238" height="931" alt="image" src="https://github.com/user-attachments/assets/05fa3168-3098-4744-936e-5302c360c4ea" />

<img width="1195" height="1373" alt="image" src="https://github.com/user-attachments/assets/f0ed07b4-e4df-45da-a123-001257488527" />


---
## 주요 기능

* **실시간 데이터 수집**: CAN 버스를 통해 ECU 데이터(RPM, 속도, 온도 등)와 GPS, 가속도계(ADXL345) 데이터를 실시간으로 수집합니다.
* **원격 데이터 전송**: 수집된 데이터를 MQTT 프로토콜을 사용하여 인터넷을 통해 원격 서버로 전송합니다.
* **웹 기반 대시보드**: Flask와 Socket.IO로 구축된 동적 웹 대시보드를 통해 어디서든 차량 상태를 실시간으로 모니터링할 수 있습니다.
* **원격 접속 터널링**: ngrok을 사용하여 고정 IP 없이도 외부 인터넷에서 라즈베리파이 서버에 안전하게 접속할 수 있습니다.
* **데이터 로깅**: 수집된 모든 데이터는 SD카드에 `.csv` 파일 형식으로 저장하여 상세한 주행 후 분석이 가능합니다.
* **자동 실행**: `systemd` 서비스를 통해 라즈베리파이 부팅 시 모든 관련 프로세스가 자동으로 실행됩니다.

---
## 시스템 아키텍처

1.  **데이터 수집 (라즈베리파이 - `main.py`)**: CAN, GPS, ADXL345 센서 데이터를 읽어와 통합 JSON 객체로 만듭니다.
2.  **데이터 발행 (MQTT)**: `main.py`가 통합된 데이터를 인터넷의 MQTT 브로커로 발행(Publish)합니다.
3.  **데이터 구독 (서버 - `telemetry_server.py`)**: Flask 웹 서버가 같은 MQTT 브로커에 접속하여 데이터를 구독(Subscribe)합니다.
4.  **실시간 시각화 (Flask + Socket.IO)**: 서버는 수신한 데이터를 즉시 Socket.IO를 통해 연결된 모든 웹 클라이언트(브라우저)에게 전달합니다.
5.  **외부 접속 (ngrok)**: ngrok이 라즈베리파이의 웹 서버(포트 5000)를 공용 인터넷 주소와 연결해주는 터널을 생성합니다.

---
## Get Started (빠른 시작)

1.  **소스 코드 복제 및 라이브러리 설치**:
    ```bash
    git clone https://github.com/hackisha/EMU-LOGGER.git
    cd EMU-LOGGER
    pip3 install -r requirements.txt
    ```

2.  **서비스 등록 및 실행**:
    ```bash
    # 서비스 파일을 시스템 폴더로 복사
    sudo cp systemd/* /etc/systemd/system/
    # 시스템 데몬 리로드
    sudo systemctl daemon-reload
    # 부팅 시 자동 실행 설정
    sudo systemctl enable telemetry.service ngrok.service
    # 지금 바로 서비스 시작
    sudo systemctl start telemetry.service ngrok.service
    ```

3.  **접속 주소(URL) 확인**:
    ```bash
    journalctl -u ngrok.service | grep "Forwarding"
    ```
    위 명령어를 통해 나타나는 `https://...ngrok-free.app` 주소를 복사합니다.

4.  **대시보드 접속**:
    외부 인터넷에 연결된 PC나 스마트폰의 웹 브라우저에서 복사한 주소로 접속합니다.

---
## 설치 및 설정 (상세)

### 하드웨어 요구사항
* Raspberry Pi Zero
* CAN 트랜시버 모듈 (MCP2515 모듈)
* GPS 수신기 모듈 (NEO-7M 등)
* 가속도 센서 (ADXL345)

---
## 사용법

설정이 완료되면 라즈베리파이를 재부팅하면 모든 서비스가 자동으로 시작됩니다.

* **서비스 상태 확인**:
    ```bash
    systemctl status telemetry.service ngrok.service
    ```

* **실시간 로그 확인**:
    ```bash
    # 데이터 수집 및 전송 로그
    journalctl -u telemetry.service -f
    
    # ngrok 접속 주소 및 로그 확인
    journalctl -u ngrok.service -f
    ```
---

