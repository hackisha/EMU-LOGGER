# gpio_ctl.py

import time

try:
    import RPi.GPIO as GPIO
    IS_RASPI = True
except (ImportError, RuntimeError):
    IS_RASPI = False

# config.py 파일에 정의된 모든 GPIO 핀 번호를 가져옵니다.
from .config import (
    BUTTON_PIN, LOGGING_LED_PIN, ERROR_LED_PIN, WIFI_LED_PIN,
    L298N_IN1, L298N_IN2
)

class GpioController:
    def __init__(self):
        self.is_raspi = IS_RASPI
        if self.is_raspi:
            try:
                # setmode를 다른 GPIO 설정보다 먼저 호출합니다.
                GPIO.setwarnings(False)
                GPIO.setmode(GPIO.BCM)

                # LED 및 버튼 핀 설정
                GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                GPIO.setup(LOGGING_LED_PIN, GPIO.OUT, initial=GPIO.LOW)
                GPIO.setup(ERROR_LED_PIN, GPIO.OUT, initial=GPIO.LOW)
                GPIO.setup(WIFI_LED_PIN, GPIO.OUT, initial=GPIO.LOW)

                # L298N 모터 드라이버 핀 설정 (ENA 핀 제외)
                GPIO.setup(L298N_IN1, GPIO.OUT, initial=GPIO.LOW)
                GPIO.setup(L298N_IN2, GPIO.OUT, initial=GPIO.LOW)

                print("GPIO 초기화 완료.")
            except RuntimeError as e:
                print(f"경고: GPIO 초기화 실패 ({e}). GPIO 기능을 비활성화합니다.")
                self.is_raspi = False

    def read_button_pressed(self) -> bool:
        """버튼이 눌렸으면 True 반환"""
        if not self.is_raspi: return False
        return GPIO.input(BUTTON_PIN) == GPIO.LOW

    def set_logging_led(self, state: bool):
        """로깅 LED를 켜거나 끕니다."""
        if not self.is_raspi: return
        GPIO.output(LOGGING_LED_PIN, GPIO.HIGH if state else GPIO.LOW)

    def blink_logging_led_once(self):
        """로깅 LED를 데이터 기록 시 잠깐 껐다 켭니다."""
        if not self.is_raspi: return
        if GPIO.input(LOGGING_LED_PIN) == GPIO.HIGH:
            GPIO.output(LOGGING_LED_PIN, GPIO.LOW)
            time.sleep(0.02)
            GPIO.output(LOGGING_LED_PIN, GPIO.HIGH)

    def set_error_led(self, state: bool):
        """에러 LED를 켜거나 끕니다."""
        if not self.is_raspi: return
        GPIO.output(ERROR_LED_PIN, GPIO.HIGH if state else GPIO.LOW)

    def set_wifi_led(self, state: bool):
        """와이파이 LED를 켜거나 끕니다."""
        if not self.is_raspi: return
        GPIO.output(WIFI_LED_PIN, GPIO.HIGH if state else GPIO.LOW)

    def set_motor_direction(self, direction: int):
        """모터의 방향을 설정합니다. (0:정지, 1:정방향, -1:역방향)"""
        if not self.is_raspi: return

        if direction == 1: # 정방향
            GPIO.output(L298N_IN1, GPIO.HIGH)
            GPIO.output(L298N_IN2, GPIO.LOW)
        elif direction == -1: # 역방향
            GPIO.output(L298N_IN1, GPIO.LOW)
            GPIO.output(L298N_IN2, GPIO.HIGH)
        else: # 정지
            GPIO.output(L298N_IN1, GPIO.LOW)
            GPIO.output(L298N_IN2, GPIO.LOW)

    def cleanup(self):
        """프로그램 종료 시 모든 GPIO 설정을 초기화합니다."""
        if self.is_raspi:
            GPIO.cleanup()
            print("GPIO 리소스 정리 완료.")
