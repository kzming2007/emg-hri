import logging
import numpy as np
import pyqtgraph as pg
from collections import deque
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QCheckBox
from PySide6.QtCore import QTimer

# 로거 설정
logger = logging.getLogger(__name__)

class RealtimePlot(QWidget):
    """
    실시간 EMG 데이터를 시각화하는 위젯 클래스.
    pyqtgraph를 사용하여 높은 성능으로 실시간 차트를 그립니다.
    """
    
    def __init__(self, parent: QWidget | None = None) -> None:
        """
        RealtimePlot 초기화 메서드.
        
        :param parent: 부모 위젯
        """
        super().__init__(parent)
        
        # 설정 상수
        self.max_points: int = 5000  # 1000Hz 기준 5초 분량 데이터
        self.sample_rate: float = 1000.0
        
        # 데이터 저장용 deque 초기화
        self.time_data: deque[float] = deque(maxlen=self.max_points)
        self.raw_data: deque[float] = deque(maxlen=self.max_points)
        self.filtered_data: deque[float] = deque(maxlen=self.max_points)
        self.envelope_data: deque[float] = deque(maxlen=self.max_points)
        
        self.sample_count: int = 0
        
        # UI 및 플롯 설정
        self._init_ui()
        self._init_plot()
        
        # 화면 갱신용 타이머 (약 33fps -> 30ms)
        self.refresh_timer: QTimer = QTimer(self)
        self.refresh_timer.timeout.connect(self._update_plot)
        self.refresh_timer.start(30)
        
    def _init_ui(self) -> None:
        """UI 컴포넌트를 초기화하고 배치합니다."""
        self.main_layout: QVBoxLayout = QVBoxLayout(self)
        
        # 체크박스 레이아웃 (채널 토글용)
        self.checkbox_layout: QHBoxLayout = QHBoxLayout()
        
        self.cb_raw: QCheckBox = QCheckBox("Raw")
        self.cb_filtered: QCheckBox = QCheckBox("Filtered")
        self.cb_envelope: QCheckBox = QCheckBox("Envelope")
        
        # 기본 상태 설정
        self.cb_raw.setChecked(False)
        self.cb_filtered.setChecked(False)
        self.cb_envelope.setChecked(True)
        
        # 체크박스 상태 변경 이벤트 연결
        self.cb_raw.stateChanged.connect(lambda: self.set_channel_visible('raw', self.cb_raw.isChecked()))
        self.cb_filtered.stateChanged.connect(lambda: self.set_channel_visible('filtered', self.cb_filtered.isChecked()))
        self.cb_envelope.stateChanged.connect(lambda: self.set_channel_visible('envelope', self.cb_envelope.isChecked()))
        
        self.checkbox_layout.addWidget(self.cb_raw)
        self.checkbox_layout.addWidget(self.cb_filtered)
        self.checkbox_layout.addWidget(self.cb_envelope)
        self.checkbox_layout.addStretch()
        
        # 플롯 위젯
        self.plot_widget: pg.PlotWidget = pg.PlotWidget()
        
        self.main_layout.addLayout(self.checkbox_layout)
        self.main_layout.addWidget(self.plot_widget)
        
    def _init_plot(self) -> None:
        """pyqtgraph 플롯을 설정합니다."""
        self.plot_widget.setBackground('#1e1e2e')  # 어두운 배경색 설정
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)  # 은은한 그리드
        self.plot_widget.setLabel('bottom', 'Time (s)')
        self.plot_widget.setLabel('left', 'Amplitude')
        self.plot_widget.setAntialiasing(True)  # 안티앨리어싱 활성화
        
        # 성능 최적화 설정
        self.plot_widget.setClipToView(True)
        self.plot_widget.setDownsampling(auto=True, mode='peak')
        
        # 뷰 설정
        self.plot_widget.setXRange(-5.0, 0.0, padding=0)
        # Y축은 데이터에 맞게 자동으로 스케일링되도록 활성화
        self.plot_widget.enableAutoRange(axis='y')
        self.plot_widget.setAutoVisible(y=True)
        
        # 펜 캐싱 및 곡선 생성
        pen_raw = pg.mkPen(color='#e06c75', width=1.5)
        pen_filtered = pg.mkPen(color='#61afef', width=1.5)
        pen_envelope = pg.mkPen(color='#98c379', width=1.5)
        
        self.curve_raw = self.plot_widget.plot(pen=pen_raw, name='Raw')
        self.curve_filtered = self.plot_widget.plot(pen=pen_filtered, name='Filtered')
        self.curve_envelope = self.plot_widget.plot(pen=pen_envelope, name='Envelope')
        
        # 초기 표시 상태 설정
        self.curve_raw.setVisible(self.cb_raw.isChecked())
        self.curve_filtered.setVisible(self.cb_filtered.isChecked())
        self.curve_envelope.setVisible(self.cb_envelope.isChecked())
        
    def add_data(self, raw: float, filtered: float, envelope: float) -> None:
        """
        새로운 EMG 데이터를 큐에 추가합니다.
        실제 화면 갱신은 QTimer에 의해 _update_plot에서 배치로 이루어집니다.
        
        :param raw: 원본 데이터 값
        :param filtered: 필터링된 데이터 값
        :param envelope: 포락선 데이터 값
        """
        current_time = self.sample_count / self.sample_rate
        
        self.time_data.append(current_time)
        self.raw_data.append(raw)
        self.filtered_data.append(filtered)
        self.envelope_data.append(envelope)
        
        self.sample_count += 1

    def _update_plot(self) -> None:
        """타이머에 의해 주기적으로 호출되어 플롯을 갱신합니다."""
        if not self.time_data:
            return
            
        # 리스트로 변환 및 x축 데이터를 최신 데이터 기준 상대 시간(최근 5초)으로 변환
        x_data = np.array(self.time_data)
        latest_time = x_data[-1]
        x_relative = x_data - latest_time  # 가장 최근 데이터가 0, 이전 데이터는 음수 시간
        
        if self.cb_raw.isChecked():
            self.curve_raw.setData(x_relative, np.array(self.raw_data))
            
        if self.cb_filtered.isChecked():
            self.curve_filtered.setData(x_relative, np.array(self.filtered_data))
            
        if self.cb_envelope.isChecked():
            self.curve_envelope.setData(x_relative, np.array(self.envelope_data))
            
    def set_channel_visible(self, channel: str, visible: bool) -> None:
        """
        특정 채널의 플롯 표시 여부를 설정합니다.
        
        :param channel: 채널 이름 ('raw', 'filtered', 'envelope')
        :param visible: 표시 여부
        """
        if channel == 'raw':
            self.curve_raw.setVisible(visible)
        elif channel == 'filtered':
            self.curve_filtered.setVisible(visible)
        elif channel == 'envelope':
            self.curve_envelope.setVisible(visible)
        else:
            logger.warning(f"Unknown channel: {channel}")
            
    def clear(self) -> None:
        """모든 데이터와 차트를 초기화합니다."""
        self.time_data.clear()
        self.raw_data.clear()
        self.filtered_data.clear()
        self.envelope_data.clear()
        self.sample_count = 0
        
        self.curve_raw.setData([], [])
        self.curve_filtered.setData([], [])
        self.curve_envelope.setData([], [])
        logger.info("Plot data cleared.")
