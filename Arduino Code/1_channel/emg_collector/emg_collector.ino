/*
 * EMG Data Collection Firmware
 * 센서: SZH-GJD001 (건식 전극 sEMG 모듈)  /  보드: Arduino Uno
 *
 * 개선 사항
 *  - micros() 스케줄링으로 "실제" 1000Hz 고정 (delayMicroseconds 고정 대기 제거)
 *  - Serial 500000 baud (115200으로는 1000Hz 3열 전송 불가)
 *  - filtered = 선형 필터 신호  -> ML 특징(RMS/MAV/IEMG)은 이 열로 계산
 *  - envelope = filtered^2      -> 그래프 표시 전용 (특징 계산에는 쓰지 말 것)
 *  - 출력 포맷: raw,filtered,envelope  (기존 Python GUI 3열 파서와 호환)
 */

#if defined(ARDUINO) && ARDUINO >= 100
#include "Arduino.h"
#else
#include "WProgram.h"
#endif

#include "EMGFilters.h"

#define SensorInputPin A0
#define BAUD           500000        // Python serial 쪽도 반드시 500000으로 맞출 것

EMGFilters       myFilter;
SAMPLE_FREQUENCY sampleRate = SAMPLE_FREQ_1000HZ;
NOTCH_FREQUENCY  humFreq    = NOTCH_FREQ_60HZ;   // 한국 전원 = 60Hz

const unsigned long PERIOD_US = 1000000UL / 1000;  // 1000Hz -> 1000us
unsigned long nextSample;

void setup() {
    // init(샘플레이트, 노치주파수, 노치ON, 로우패스ON, 하이패스ON)
    myFilter.init(sampleRate, humFreq, true, true, true);

    Serial.begin(BAUD);

    // (Uno/Nano AVR 전용) ADC 프리스케일러 128 -> 16, analogRead 가속(~15us)
    // 정밀도가 더 중요하면 0x04 대신 0x05(프리스케일러 32) 사용
    ADCSRA = (ADCSRA & 0xF8) | 0x04;

    // --- (선택) ADC 해상도 향상 ---
    // 센서 출력은 0~3.0V라 기본 5V 기준전압에서는 해상도의 40%가 낭비됨.
    // AREF 핀에 3.3V를 "먼저 연결"한 경우에만 아래 두 줄의 주석을 해제할 것.
    // (연결 없이 EXTERNAL 설정 시 ADC 손상 위험)
    // analogReference(EXTERNAL);
    // for (int i = 0; i < 5; i++) analogRead(SensorInputPin);  // 전환 후 첫 샘플 버리기

    nextSample = micros();
}

void loop() {
    // 처리 시간(analogRead/필터/Serial)과 무관하게 정확히 1000Hz 유지
    if ((long)(micros() - nextSample) < 0) return;
    nextSample += PERIOD_US;

    int  raw      = analogRead(SensorInputPin);
    int  filtered = myFilter.update(raw);            // 제곱하지 않은 선형 신호
    long envelope = (long)filtered * filtered;        // 표시 전용 (제곱)

    // Python GUI 3열 포맷: raw,filtered,envelope
    Serial.print(raw);       Serial.print(',');
    Serial.print(filtered);  Serial.print(',');
    Serial.println(envelope);
}
