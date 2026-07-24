"""
애플리케이션 설정을 관리하는 모듈입니다.
"""
from dataclasses import dataclass
from enum import Enum, auto

@dataclass
class AppConfig:
    """애플리케이션 기본 설정 데이터 클래스입니다."""
    serial_port: str = ''
    baud_rate: int = 115200
    sample_rate: int = 1000
    countdown_seconds: int = 3
    relax_duration: float = 5.0
    motion_duration: float = 5.0
    transition_duration: float = 1.0
    save_dir: str = 'Data'
    plot_window_seconds: int = 5

# 근육 및 동작 상수 목록
MUSCLES = ['FDS', 'FCR', 'FCU', 'ED', 'BR', 'Custom']
MOTIONS = ['Relax', 'Fist', 'Wrist Flexion', 'Wrist Extension', 'Open Hand', 'Pinch', 'Custom']

# 애플리케이션 상수
LABEL_RELAX = 'Relax'
LABEL_TRANSITION = 'Transition'
APP_TITLE = 'EMG Data Collector'
APP_VERSION = '2.0.0'

class ExperimentPhase(Enum):
    """실험 단계를 나타내는 열거형입니다."""
    IDLE = auto()
    COUNTDOWN = auto()
    RELAX_PRE = auto()
    TRANSITION_1 = auto()
    MOTION = auto()
    TRANSITION_2 = auto()
    RELAX_POST = auto()
    DONE = auto()

# 그래프 색상 상수 (RGB 튜플)
RAW_COLOR = (200, 200, 200)       # 원시 신호 색상 (회색)
FILTERED_COLOR = (50, 150, 255)   # 필터링된 신호 색상 (파란색)
ENVELOPE_COLOR = (255, 100, 50)   # 포락선 신호 색상 (주황색)
