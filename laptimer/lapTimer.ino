
#include <WiFiS3.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// --- 사용자 설정 ---
char ssid[] = "";     // 연결할 와이파이 이름
char pass[] = ""; // 와이파이 비밀번호

const char* mqtt_server = "test.mosquitto.org";
const int mqtt_port = 1883;
const char* telemetry_topic = "car/emu/telemetry"; 

const int CDS_PIN = A0; 
const int LIGHT_THRESHOLD = 500;

// --- 클라이언트 및 전역 변수 ---
WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

unsigned long lapStartTime = 0;
unsigned long lastDetectionTime = 0;
unsigned long lastPrintTime = 0; // 디버깅 메시지 출력 시간 제어용
bool isTimerRunning = false;
int lapCount = 0;

void setup() {
  Serial.begin(115200);
  while (!Serial);

  setup_wifi();
  mqttClient.setServer(mqtt_server, mqtt_port);
  
  // <<< 요청사항 1: 센서 캘리브레이션 코드 추가 >>>
  // 초기 튜닝을 위해 5초간 현재 빛의 밝기를 출력합니다.
  Serial.println("\nCalibrating light sensor for 5 seconds...");
  Serial.println("Please shine the laser on the sensor now to check its value.");
  for(int i=0; i<50; i++){
    Serial.print("Current light value: ");
    Serial.println(analogRead(CDS_PIN));
    delay(100);
  }
  Serial.print("Calibration finished. Using threshold: ");
  Serial.println(LIGHT_THRESHOLD);
  
  Serial.println("\nLap timer ready. Waiting for the first lap...");
  lapStartTime = millis();
  isTimerRunning = true;
  lapCount = 1;
}

void loop() {
  if (!mqttClient.connected()) {
    reconnect_mqtt();
  }
  mqttClient.loop();

  int lightValue = analogRead(CDS_PIN);

  // <<< 요청사항 2: 현재 CDS 값 실시간 출력 (0.5초마다) >>>
  if (millis() - lastPrintTime > 10) {
    Serial.print("DEBUG: Current light value = ");
    Serial.println(lightValue);
    lastPrintTime = millis();
  }

  // 빛이 임계값보다 어두워지고, 마지막 감지로부터 2초가 지났을 경우
  if (lightValue < LIGHT_THRESHOLD) {
    if (isTimerRunning) {
      unsigned long currentTime = millis();
      unsigned long lapTime = currentTime - lapStartTime;

      Serial.print("--- Lap ");
      Serial.print(lapCount);
      Serial.print(" Detected! --- Lap Time: ");
      Serial.print(lapTime);
      Serial.println(" ms");

      publishLapTime(lapCount, lapTime);

      lapStartTime = currentTime;
      lastDetectionTime = currentTime;
      lapCount++;
    }
  }
}

void setup_wifi() {
  delay(10);
  Serial.print("Connecting to Wi-Fi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, pass);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Connected!");
}

void reconnect_mqtt() {
  while (!mqttClient.connected()) {
    Serial.print("Attempting MQTT connection...");
    String clientId = "ArduinoLapTimer-" + String(random(0xffff), HEX);
    if (mqttClient.connect(clientId.c_str())) {
      Serial.println("connected!");
    } else {
      Serial.print("failed, rc=");
      Serial.print(mqttClient.state());
      Serial.println(" try again in 5 seconds");
      delay(5000);
    }
  }
}

void publishLapTime(int lap, unsigned long time) {
  JsonDocument doc;
  doc["source"] = "ArduinoLapTimer(CDS)";
  doc["lap"] = lap;
  doc["lapTime_ms"] = time;
  
  // 데이터 구조 통일성을 위한 빈 객체
  doc.createNestedObject("can");
  doc.createNestedObject("gps");
  doc.createNestedObject("accel");

  char jsonBuffer[256];
  serializeJson(doc, jsonBuffer);

  Serial.print("Publishing message: ");
  Serial.println(jsonBuffer);
  
  mqttClient.publish(telemetry_topic, jsonBuffer);
  delay(3000);
}
