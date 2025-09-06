#include <LiquidCrystal_I2C.h>

#define DEBOUNCE_DELAY 30 // 디바운스 지연 시간 조정

// --- 주변 장치 및 핀 설정 ---
LiquidCrystal_I2C lcd(0x27, 16, 2);

// 출력 핀
const byte fuelCutPin       = 5;
const byte shiftUpPin       = 6;
const byte shiftDownPin     = 7;
const byte l298n2_IN2       = 3;
const byte l298n2_IN4       = 4;

// 입력 핀 (버튼)
const byte shiftUpButtonPin       = 9;
const byte shiftUpIdleButtonPin   = 10;
const byte shiftDownButtonPin     = 11;
const byte shiftDownIdleButtonPin = 12;

// --- 상태 머신 정의 ---
enum ShiftState {
  S_IDLE,
  S_UP_SHIFT_FUEL_CUT,
  S_UP_SHIFT_CYLINDER_ACTIVE,
  S_IDLE_UP_SHIFT_ACTIVE,
  S_IDLE_DOWN_SHIFT_ACTIVE
};
ShiftState currentShiftState = S_IDLE;

// --- Button 구조체 및 상태 변수 ---
struct Button {
  const byte pin;
  bool lastReading;
  bool debouncedState;
  unsigned long lastDebounceTime;

  Button(byte p) : pin(p), lastReading(HIGH), debouncedState(HIGH), lastDebounceTime(0) {}
};

Button shiftUpButton(shiftUpButtonPin);
Button shiftUpIdleButton(shiftUpIdleButtonPin);
Button shiftDownButton(shiftDownButtonPin);
Button shiftDownIdleButton(shiftDownIdleButtonPin);

// --- 전역 변수 ---
unsigned int fuelCutTime    = 0;
unsigned int cylinderTime   = 0;
unsigned int cylinderDelay  = 0;

unsigned long stateChangeTime     = 0;
unsigned long lastLcdUpdateTime   = 0;
const unsigned int updateLCDInterval = 500;


// 함수 선언
void updateShiftController();
bool wasPressed(Button &btn);
void updateAllButtons();
void handleShiftDown();


void setup() {
  Serial.begin(9600);

  // LCD 초기화
  lcd.begin();
  lcd.backlight();

  // 출력 핀 설정
  pinMode(fuelCutPin, OUTPUT);
  digitalWrite(fuelCutPin, HIGH);
  pinMode(shiftUpPin, OUTPUT);
  pinMode(shiftDownPin, OUTPUT);
  pinMode(l298n2_IN2, OUTPUT);
  pinMode(l298n2_IN4, OUTPUT);

  // 입력 핀(풀업)
  pinMode(shiftUpButton.pin,       INPUT_PULLUP);
  pinMode(shiftUpIdleButton.pin,   INPUT_PULLUP);
  pinMode(shiftDownButton.pin,     INPUT_PULLUP);
  pinMode(shiftDownIdleButton.pin, INPUT_PULLUP);

  stopCylinders();
}

void loop() {
  unsigned long currentTime = millis();

  // 모든 버튼의 디바운싱 상태를 매 루프마다 업데이트
  updateAllButtons();

  // 아날로그 읽어서 0~150으로 매핑
  fuelCutTime   = map(analogRead(A0), 0, 1023, 0, 300);
  cylinderTime  = map(analogRead(A2), 0, 1023, 0, 300);
  cylinderDelay = map(analogRead(A1), 0, 1023, 0, 300);

  // 쉬프트 다운 로직 처리 (상태 머신과 별개로 동작)
  handleShiftDown();

  // 상태 머신 (쉬프트 다운 제외)
  updateShiftController();

  // LCD
  if (currentTime - lastLcdUpdateTime >= updateLCDInterval) {
    updateLCD();
    lastLcdUpdateTime = currentTime;
  }
}

void handleShiftDown() {
  // 다른 변속 동작이 없을 때(IDLE 상태일 때)만 쉬프트 다운 로직을 처리
  if (currentShiftState == S_IDLE) {
    // 버튼을 처음 누르는 순간(Falling Edge)에 로그 출력
    if (wasPressed(shiftDownButton)) {
      Serial.println("ShiftDown: Button Pressed");
    }

    // 버튼이 눌려있는 동안(debouncedState가 LOW) 실린더를 계속 동작시킴
    if (shiftDownButton.debouncedState == LOW) {
      shiftCylinderDown();
    }
    // 버튼이 눌려있지 않으면 실린더를 멈춤
    else {
      digitalWrite(shiftDownPin, LOW);
      digitalWrite(l298n2_IN4, LOW);
    }
  }
}

void updateShiftController() {
  unsigned long currentTime = millis();

  switch (currentShiftState) {
    case S_IDLE:
      if (wasPressed(shiftUpButton)) {
        Serial.println("ShiftUp: Fuel Cut Start");
        digitalWrite(fuelCutPin, LOW);
        stopCylinders();
        stateChangeTime = currentTime;
        currentShiftState = S_UP_SHIFT_FUEL_CUT;
      }
      else if (wasPressed(shiftUpIdleButton)) {
        Serial.println("Idle ShiftUp: Cylinder UP");
        shiftCylinderUp();
        stateChangeTime = currentTime;
        currentShiftState = S_IDLE_UP_SHIFT_ACTIVE;
      }
      else if (wasPressed(shiftDownIdleButton)) {
        Serial.println("Idle ShiftDown: Cylinder DOWN");
        shiftCylinderDown();
        stateChangeTime = currentTime;
        currentShiftState = S_IDLE_DOWN_SHIFT_ACTIVE;
      }
      break;

    case S_UP_SHIFT_FUEL_CUT:
      if (currentTime - stateChangeTime >= cylinderDelay) {
        Serial.println("ShiftUp: Cylinder UP");
        shiftCylinderUp();
        stateChangeTime = currentTime;
        currentShiftState = S_UP_SHIFT_CYLINDER_ACTIVE;
      }
      break;

    case S_UP_SHIFT_CYLINDER_ACTIVE:
      if (currentTime - stateChangeTime >= cylinderTime) {
        Serial.println("ShiftUp: Complete");
        stopCylinders();
        digitalWrite(fuelCutPin, HIGH);
        currentShiftState = S_IDLE;
      }
      break;

    case S_IDLE_UP_SHIFT_ACTIVE:
      if (currentTime - stateChangeTime >= cylinderTime) {
        Serial.println("Idle ShiftUp: Complete");
        stopCylinders();
        currentShiftState = S_IDLE;
      }
      break;

    case S_IDLE_DOWN_SHIFT_ACTIVE:
      if (currentTime - stateChangeTime >= cylinderTime) {
        Serial.println("Idle ShiftDown: Complete");
        stopCylinders();
        currentShiftState = S_IDLE;
      }
      break;
  }
}

void updateAllButtons() {
    wasPressed(shiftUpButton);
    wasPressed(shiftUpIdleButton);
    wasPressed(shiftDownButton);
    wasPressed(shiftDownIdleButton);
}

bool wasPressed(Button &btn) {
  bool oldState = btn.debouncedState;
  bool reading  = digitalRead(btn.pin);

  if (reading != btn.lastReading) {
    btn.lastDebounceTime = millis();
  }
  if (millis() - btn.lastDebounceTime > DEBOUNCE_DELAY) {
    btn.debouncedState = reading;
  }
  btn.lastReading = reading;

  return (oldState == HIGH && btn.debouncedState == LOW);
}

void updateLCD() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("FuelCut: ");
  lcd.print(fuelCutTime);
  lcd.setCursor(0, 1);
  lcd.print("Cyl D:");
  lcd.print(cylinderDelay);
  lcd.print(" T:");
  lcd.print(cylinderTime);
}

void shiftCylinderUp() {
  digitalWrite(shiftUpPin, HIGH);
  digitalWrite(l298n2_IN2, LOW);
}

void shiftCylinderDown() {
  digitalWrite(shiftDownPin, HIGH);
  digitalWrite(l298n2_IN4, LOW);
}

void stopCylinders() {
  digitalWrite(shiftUpPin, LOW);
  digitalWrite(shiftDownPin, LOW);
  digitalWrite(l298n2_IN2, LOW);
  digitalWrite(l298n2_IN4, LOW);
  Serial.println("Cylinder STOP");
}
