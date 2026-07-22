// 구버전 및 신버전 아두이노 IDE 호환성을 위한 헤더 파일 포함
#if defined(ARDUINO) && ARDUINO >= 100
#include "Arduino.h"
#else
#include "WProgram.h"
#endif

#include "EMGFilters.h" // 근전도 센서의 노이즈를 제거하기 위한 필터 라이브러리

#define TIMING_DEBUG 1        // 시리얼 모니터에 값을 출력할지 결정하는 플래그 (1: 출력, 0: 출력 안 함)
#define SensorInputPin A0     // 근전도 센서가 연결된 아두이노의 아날로그 핀 번호 (A0)

EMGFilters myFilter;          // 필터 기능을 사용할 객체 생성
int sampleRate = SAMPLE_FREQ_1000HZ; // 샘플링 속도 설정 (1초에 1000번 측정)
int humFreq = NOTCH_FREQ_60HZ;       // 대한민국 전원 주파수(60Hz)에 맞춘 Notch Filter

static int Threshold = 0;      // 노이즈를 무시하기 위한 임계값 (현재 0으로 설정되어 모든 신호 통과)

unsigned long timeStamp;      // 코드 실행 시간을 계산하기 위한 변수
unsigned long timeBudget;     // 1회 측정에 할당된 목표 시간

void setup() {
    // 필터 초기화: (샘플링속도, 노이즈주파수, LowPass필터 켜기, HighPass필터 켜기, 기타 필터 켜기)
    myFilter.init(sampleRate, humFreq, true, true, true);

    // PC와 통신하기 위해 시리얼 통신 시작 (통신 속도: 115200)
    Serial.begin(115200);

    // 1초(1,000,000 마이크로초) / 1000Hz = 1000 마이크로초 (1밀리초마다 측정해야 함을 계산)
    timeBudget = 1e6 / sampleRate; 
}

void loop() {
    timeStamp = micros(); // 현재 시간을 마이크로초 단위로 저장

    int Value = analogRead(SensorInputPin); // A0 핀에서 근전도 센서 값을 읽어옴

    // 읽어온 값을 필터에 통과시켜 노이즈가 제거된 깔끔한 값을 얻음
    int DataAfterFilter = myFilter.update(Value); 
    
    // 필터링된 값을 제곱하여 신호의 파워(크기)를 구함 (음수도 양수가 되고 큰 값은 더 커짐)
    long envelope = (long)DataAfterFilter * DataAfterFilter;
    
    // 계산된 값이 임계값(Threshold)보다 크면 그대로 사용, 작으면 0으로 만듦 (잔잔한 노이즈 제거)
    envelope = (envelope > Threshold) ? envelope : 0;

    timeStamp = micros() - timeStamp; // 센서 읽기 및 계산에 걸린 시간 측정

    // TIMING_DEBUG가 1일 경우 처리된 근전도 값을 시리얼 모니터로 전송
    if (TIMING_DEBUG) {
        Serial.println(envelope); 
    }

    // 다음 측정까지 대기 (1000Hz를 맞추기 위해 약 500 마이크로초 쉼)
    delayMicroseconds(500);
}