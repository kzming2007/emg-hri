# EMG Data Collector

## 1. 개요
아두이노 기반 표면 근전도(sEMG) 데이터 수집 애플리케이션입니다. 생체 신호 연구 및 머신러닝 분석을 위한 고품질 EMG 데이터를 수집, 시각화하고 저장합니다.

## 2. 기능
- 실시간 sEMG 신호 수집 및 시각화
- 3초 카운트다운을 포함한 자동화된 실험 프로토콜
- 피험자, 근육, 동작 별 메타데이터 관리 및 저장
- Raw, Filtered, Envelope 신호 동시 수집
- 수집된 데이터의 실시간 통계 분석 (RMS, MAV, IEMG 등)
- 구조화된 CSV 파일 형식으로 데이터 자동 저장

## 3. 시스템 요구사항
- Python 3.12+
- 운영체제: Windows, macOS, Linux (모두 지원)
- 메모리: 4GB RAM 이상
- 해상도: 1920x1080 이상 권장

## 4. 설치 방법
```bash
cd EMG_Data_Collector
pip install -r requirements.txt
```

## 5. 실행 방법
```bash
python main.py
```

## 6. Arduino 설정
- **보드**: Arduino Uno (또는 호환 보드)
- **라이브러리**: `EMGFilters` 라이브러리 설치 필요
- **Baud Rate**: `115200` bps
- **센서 핀**: `A0` (EMG 센서 아날로그 입력)
- **출력 포맷**: `Raw,Filtered,Envelope` (Comma separated values)

## 7. 사용 방법
1. 아두이노 보드를 USB로 PC에 연결합니다.
2. 애플리케이션 우측 상단의 제어반에서 **COM 포트**를 선택하고 **연결(Connect)** 버튼을 클릭합니다.
3. 실험 정보 섹션에서 현재 **근육(Muscle)**과 **동작(Action)**을 선택/입력합니다.
4. **Trial 번호**를 설정합니다. (기본값: 1, 자동으로 증가)
5. **기록 시작(Start Recording)** 버튼을 클릭합니다.
6. 3초 카운트다운(준비) 후 설정된 시간 동안 자동으로 데이터가 수집됩니다.
7. 수집 완료 후 자동으로 데이터 파일이 저장되고, 다음 Trial을 위해 대기합니다.

## 8. 데이터 폴더 구조
```
data/
└── {Subject_ID}/
    └── {Muscle}_{Action}/
        ├── 01_raw.csv
        ├── 01_stats.csv
        ├── 02_raw.csv
        └── 02_stats.csv
```
데이터는 피험자(Subject) 하위에 근육과 동작 조합으로 분류되어 체계적으로 관리됩니다.

## 9. CSV 파일 형식
수집된 실시간 시계열 데이터는 다음과 같은 헤더를 가지는 CSV 형식으로 저장됩니다.
`Timestamp, Raw, Filtered, Envelope`

## 10. 통계 분석 항목
저장된 각 Trial에 대한 통계 정보(stats.csv)에는 다음 항목이 포함됩니다.
- **Mean**: 평균값
- **Max**: 최댓값
- **Min**: 최솟값
- **Std**: 표준편차
- **RMS (Root Mean Square)**: 신호의 실효값, 근육의 수축력을 나타내는 주요 지표
- **MAV (Mean Absolute Value)**: 평균 절대값, 근활성도의 척도
- **IEMG (Integrated EMG)**: 누적 근전도 값, 해당 구간 동안의 총 근육 활성량

## 11. 트러블슈팅
- **COM 포트가 보이지 않을 때**: 아두이노 USB 케이블 연결을 확인하고, 새로고침(Refresh) 버튼을 클릭하세요. 드라이버가 정상적으로 설치되었는지 장치 관리자를 확인합니다.
- **연결이 끊어질 때**: USB 케이블 불량이나 외부 노이즈 문제일 수 있습니다. 케이블을 교체하거나 다른 USB 포트에 연결해 보세요.
- **데이터가 수신되지 않을 때**: 아두이노의 Baud Rate 설정(115200)이 맞는지, 센서가 A0 핀에 올바르게 연결되어 있는지 확인하세요. 시리얼 모니터로 직접 데이터를 확인해 보는 것도 좋습니다.

## 12. 향후 확장 계획
- **다중 EMG 채널**: 최대 4채널 동시 수집 지원
- **무선 통신**: Bluetooth 또는 Wi-Fi 모듈 연동을 통한 무선 데이터 수집
- **머신러닝 모듈**: 수집된 데이터를 바탕으로 실시간 동작 분류 모델 학습 및 평가
- **실시간 예측 모드**: 수집된 데이터에 학습된 모델을 적용하여 동작 의도를 실시간으로 추론

## 13. 프로젝트 구조
```
EMG_Data_Collector/
├── gui/
│   ├── main_window.py       # 메인 GUI 창
│   ├── control_panel.py     # 제어 및 설정 패널
│   ├── plot_widget.py       # 데이터 시각화 위젯
│   └── info_panel.py        # 시스템 상태 및 정보 패널
├── core/
│   ├── serial_manager.py    # 시리얼 통신 관리
│   ├── data_processor.py    # 데이터 파싱 및 큐 관리
│   ├── experiment_runner.py # 실험 프로토콜(카운트다운 등) 제어
│   └── file_manager.py      # 데이터 저장 및 폴더 관리
├── logs/                    # 애플리케이션 로그 폴더
├── data/                    # 수집된 측정 데이터 폴더
├── main.py                  # 프로그램 실행 진입점
├── requirements.txt         # 파이썬 패키지 의존성
└── README.md                # 프로젝트 설명서
```

## 14. 라이선스
이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자유로운 사용 및 수정이 가능합니다.
