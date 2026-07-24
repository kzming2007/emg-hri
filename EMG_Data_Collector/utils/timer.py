"""
실험 타이머 및 시퀀스를 제어하는 모듈입니다.

실험 프로토콜:
  COUNTDOWN(3s) → RELAX_PRE(5s) → TRANSITION_1(1s) → MOTION(5s)
  → TRANSITION_2(1s) → RELAX_POST(5s) → DONE
"""
import time
from typing import Optional
from PySide6.QtCore import QObject, QTimer, Signal
from .config import ExperimentPhase, AppConfig, LABEL_RELAX, LABEL_TRANSITION


class ExperimentTimer(QObject):
    """
    실험 시퀀스를 관리하고 시간을 측정하는 타이머 클래스입니다.
    Transition 구간을 포함한 7단계 프로토콜을 제어합니다.
    """
    # 신호 정의 (phase_name, label)
    phase_changed = Signal(str, str)
    # 남은 시간 (초 단위의 float)
    countdown_tick = Signal(float)
    # 실험 종료 신호
    experiment_finished = Signal()

    def __init__(self, config: Optional[AppConfig] = None, parent: Optional[QObject] = None) -> None:
        """
        초기화 메서드입니다.

        Args:
            config: 애플리케이션 설정 객체
            parent: 부모 QObject
        """
        super().__init__(parent)
        self.config = config or AppConfig()

        self.timer = QTimer(self)
        self.timer.setInterval(100)  # 100ms 간격으로 업데이트하여 부드러운 UI 갱신
        self.timer.timeout.connect(self._update_timer)

        self.current_phase: ExperimentPhase = ExperimentPhase.IDLE
        self.motion_name: str = ""

        self.phase_start_time: float = 0.0
        self.phase_duration: float = 0.0

    def start(self, motion_name: str) -> None:
        """
        실험 시퀀스를 시작합니다.

        Args:
            motion_name: 수행할 동작의 이름
        """
        self.motion_name = motion_name
        self._set_phase(ExperimentPhase.COUNTDOWN)
        self.timer.start()

    def stop(self) -> None:
        """실험을 강제로 중지합니다."""
        self.timer.stop()
        self.current_phase = ExperimentPhase.IDLE

    def get_current_phase(self) -> ExperimentPhase:
        """현재 실험 단계를 반환합니다."""
        return self.current_phase

    def get_remaining_time(self) -> float:
        """현재 단계의 남은 시간을 반환합니다."""
        if self.current_phase == ExperimentPhase.IDLE:
            return 0.0
        elapsed = time.perf_counter() - self.phase_start_time
        remaining = self.phase_duration - elapsed
        return max(0.0, remaining)

    def _set_phase(self, phase: ExperimentPhase) -> None:
        """
        다음 실험 단계로 전환합니다.

        Args:
            phase: 전환할 실험 단계
        """
        self.current_phase = phase
        self.phase_start_time = time.perf_counter()

        label = ""
        if phase == ExperimentPhase.COUNTDOWN:
            self.phase_duration = self.config.countdown_seconds
            label = ""
        elif phase == ExperimentPhase.RELAX_PRE:
            self.phase_duration = self.config.relax_duration
            label = LABEL_RELAX
        elif phase == ExperimentPhase.TRANSITION_1:
            self.phase_duration = self.config.transition_duration
            label = LABEL_TRANSITION
        elif phase == ExperimentPhase.MOTION:
            self.phase_duration = self.config.motion_duration
            label = self.motion_name
        elif phase == ExperimentPhase.TRANSITION_2:
            self.phase_duration = self.config.transition_duration
            label = LABEL_TRANSITION
        elif phase == ExperimentPhase.RELAX_POST:
            self.phase_duration = self.config.relax_duration
            label = LABEL_RELAX
        elif phase == ExperimentPhase.DONE:
            self.timer.stop()
            self.experiment_finished.emit()
            return

        self.phase_changed.emit(phase.name, label)

    def _update_timer(self) -> None:
        """타이머 타임아웃 시 호출되는 메서드입니다. 남은 시간을 계산하고 단계를 전환합니다."""
        remaining = self.get_remaining_time()
        self.countdown_tick.emit(remaining)

        if remaining <= 0:
            self._next_phase()

    def _next_phase(self) -> None:
        """현재 단계가 끝난 후 다음 단계로 넘어갑니다."""
        if self.current_phase == ExperimentPhase.COUNTDOWN:
            self._set_phase(ExperimentPhase.RELAX_PRE)
        elif self.current_phase == ExperimentPhase.RELAX_PRE:
            self._set_phase(ExperimentPhase.TRANSITION_1)
        elif self.current_phase == ExperimentPhase.TRANSITION_1:
            self._set_phase(ExperimentPhase.MOTION)
        elif self.current_phase == ExperimentPhase.MOTION:
            self._set_phase(ExperimentPhase.TRANSITION_2)
        elif self.current_phase == ExperimentPhase.TRANSITION_2:
            self._set_phase(ExperimentPhase.RELAX_POST)
        elif self.current_phase == ExperimentPhase.RELAX_POST:
            self._set_phase(ExperimentPhase.DONE)
