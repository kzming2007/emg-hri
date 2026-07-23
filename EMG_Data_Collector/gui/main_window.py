import sys
import os
import logging
import threading
import importlib
from pathlib import Path
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                                QLabel, QComboBox, QPushButton, QSpinBox,
                                QLineEdit, QGroupBox, QFrame, QStatusBar,
                                QFileDialog, QMessageBox, QApplication)
from PySide6.QtCore import Qt, QTimer, Slot, Signal, QObject, QThread
from PySide6.QtGui import QFont, QColor

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.config import AppConfig, MUSCLES, MOTIONS, LABEL_RELAX, APP_TITLE, ExperimentPhase
from utils.timer import ExperimentTimer
from graphs.realtime_plot import RealtimePlot
from gui.dialogs import CustomInputDialog, RecordingCompleteDialog
from recorder.recorder import DataRecorder
from analysis.analyzer import EMGAnalyzer

from comm.serial_manager import SerialManager


class AnalysisWorker(QObject):
    """백그라운드에서 데이터를 분석하기 위한 워커 클래스"""
    finished = Signal(dict, object)
    error = Signal(str)

    def __init__(self, data_frame, save_dir, muscle, motion, trial):
        super().__init__()
        self.data_frame = data_frame
        self.save_dir = save_dir
        self.muscle = muscle
        self.motion = motion
        self.trial = trial

    def run(self):
        try:
            analyzer = EMGAnalyzer(self.data_frame, self.save_dir, self.muscle, self.motion, self.trial)
            stats = analyzer.analyze()
            analyzer.save_summary(stats)
            analyzer.save_graphs()
            self.finished.emit(stats, self.save_dir)
        except Exception as e:
            logging.error(f"분석 중 오류 발생: {e}")
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    """메인 GUI 창"""
    
    # UI State Constants
    STATE_DISCONNECTED = 0
    STATE_CONNECTED = 1
    STATE_RECORDING = 2
    STATE_ANALYZING = 3

    def __init__(self):
        super().__init__()
        self.config = AppConfig()
        
        # Core Components
        self.serial_manager = SerialManager()
        self.experiment_timer = ExperimentTimer(self.config)
        self.recorder = None
        self._recording_active = False  # COUNTDOWN 동안 데이터 기록 방지용 플래그
        
        # State
        self.current_state = self.STATE_DISCONNECTED
        self.sample_count = 0
        
        # Data rate timer
        self.rate_timer = QTimer(self)
        self.rate_timer.timeout.connect(self._update_data_rate)
        self.rate_timer.start(1000)
        self.current_rate = 0
        
        self._init_ui()
        self._connect_signals()
        self._apply_styles()
        self._update_ui_state()

    def _init_ui(self):
        """UI 컴포넌트 초기화"""
        self.setWindowTitle(APP_TITLE)
        self.resize(1200, 800)
        
        # Main Widget and Layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15)

        # Left Panel (Fixed Width)
        left_panel = QFrame()
        left_panel.setFixedWidth(300)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(15)

        # 1. Connection Section
        conn_group = QGroupBox("연결 설정")
        conn_layout = QVBoxLayout()
        
        port_layout = QHBoxLayout()
        self.port_combo = QComboBox()
        self._refresh_ports()
        
        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setFixedWidth(30)
        self.refresh_btn.clicked.connect(self._refresh_ports)
        
        port_layout.addWidget(QLabel("COM Port:"))
        port_layout.addWidget(self.port_combo)
        port_layout.addWidget(self.refresh_btn)
        
        self.connect_btn = QPushButton("연결")
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        
        conn_layout.addLayout(port_layout)
        conn_layout.addWidget(self.connect_btn)
        conn_group.setLayout(conn_layout)

        # 2. Experiment Section
        exp_group = QGroupBox("실험 설정")
        exp_layout = QVBoxLayout()
        
        self.muscle_combo = QComboBox()
        self.muscle_combo.addItems(MUSCLES)
        self.muscle_combo.currentTextChanged.connect(self._on_muscle_changed)
        
        self.motion_combo = QComboBox()
        self.motion_combo.addItems(MOTIONS)
        self.motion_combo.currentTextChanged.connect(self._on_motion_changed)
        
        self.trial_spin = QSpinBox()
        self.trial_spin.setRange(1, 999)
        self.trial_spin.setValue(1)
        
        save_layout = QHBoxLayout()
        self.save_dir_edit = QLineEdit(str(self.config.save_dir))
        self.save_dir_edit.setReadOnly(True)
        self.browse_btn = QPushButton("찾아보기")
        self.browse_btn.clicked.connect(self._browse_save_dir)
        save_layout.addWidget(self.save_dir_edit)
        save_layout.addWidget(self.browse_btn)

        exp_layout.addWidget(QLabel("근육 (Muscle):"))
        exp_layout.addWidget(self.muscle_combo)
        exp_layout.addWidget(QLabel("동작 (Motion):"))
        exp_layout.addWidget(self.motion_combo)
        exp_layout.addWidget(QLabel("시도 횟수 (Trial):"))
        exp_layout.addWidget(self.trial_spin)
        exp_layout.addWidget(QLabel("저장 경로:"))
        exp_layout.addLayout(save_layout)
        exp_group.setLayout(exp_layout)

        # 3. Control Section
        ctrl_group = QGroupBox("제어")
        ctrl_layout = QVBoxLayout()
        
        self.start_btn = QPushButton("기록 시작")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.clicked.connect(self._on_start_recording)
        
        self.stop_btn = QPushButton("기록 중지")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.clicked.connect(self._on_stop_recording)
        
        self.reset_btn = QPushButton("초기화")
        self.reset_btn.setMinimumHeight(30)
        self.reset_btn.clicked.connect(self._on_reset)
        
        ctrl_layout.addWidget(self.start_btn)
        ctrl_layout.addWidget(self.stop_btn)
        ctrl_layout.addWidget(self.reset_btn)
        ctrl_group.setLayout(ctrl_layout)

        left_layout.addWidget(conn_group)
        left_layout.addWidget(exp_group)
        left_layout.addWidget(ctrl_group)
        left_layout.addStretch()

        # Center/Right Area
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Phase Display
        self.phase_frame = QFrame()
        self.phase_frame.setObjectName("phaseFrame")
        self.phase_frame.setFixedHeight(120)
        phase_layout = QVBoxLayout(self.phase_frame)
        
        self.phase_label = QLabel("준비")
        self.phase_label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(48)
        font.setBold(True)
        self.phase_label.setFont(font)
        
        self.countdown_label = QLabel("")
        self.countdown_label.setAlignment(Qt.AlignCenter)
        count_font = QFont()
        count_font.setPointSize(36)
        self.countdown_label.setFont(count_font)
        
        phase_layout.addWidget(self.phase_label)
        phase_layout.addWidget(self.countdown_label)
        
        # Real-time Plot
        self.plot_widget = RealtimePlot()
        
        right_layout.addWidget(self.phase_frame)
        right_layout.addWidget(self.plot_widget)

        # Combine Left and Right
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, 1)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.status_conn_indicator = QLabel("● 분리됨")
        self.status_conn_indicator.setStyleSheet("color: #e05252;")
        self.status_rate_label = QLabel("0 샘플/초")
        
        self.status_bar.addWidget(self.status_conn_indicator)
        self.status_bar.addPermanentWidget(self.status_rate_label)

    def _connect_signals(self):
        """시그널 및 슬롯 연결"""
        self.serial_manager.data_received.connect(self._on_data_received)
        self.serial_manager.connection_changed.connect(self._on_connection_changed)
        self.serial_manager.error_occurred.connect(self._on_error)
        
        self.experiment_timer.phase_changed.connect(self._on_phase_changed)
        self.experiment_timer.countdown_tick.connect(self._on_countdown_tick)
        self.experiment_timer.experiment_finished.connect(self._on_experiment_finished)

    def _apply_styles(self):
        """다크 테마 QSS 적용"""
        qss = """
        QMainWindow, QWidget {
            background-color: #1e1e2e;
            color: #e0e0e0;
        }
        QGroupBox {
            border: 1px solid #3d3f43;
            border-radius: 5px;
            margin-top: 1ex;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top center;
            padding: 0 3px;
        }
        QComboBox, QSpinBox, QLineEdit {
            background-color: #2b2d30;
            border: 1px solid #3d3f43;
            border-radius: 3px;
            padding: 5px;
            color: #e0e0e0;
        }
        QPushButton {
            background-color: #2b2d30;
            border: 1px solid #3d3f43;
            border-radius: 4px;
            padding: 5px 10px;
            color: #e0e0e0;
        }
        QPushButton:hover {
            background-color: #3d3f43;
        }
        QPushButton:disabled {
            color: #666666;
            background-color: #1e1e2e;
        }
        QPushButton#startBtn {
            background-color: #2b4a3a;
            border: 1px solid #4ec54e;
            color: #4ec54e;
            font-weight: bold;
        }
        QPushButton#startBtn:hover {
            background-color: #3b6a4a;
        }
        QPushButton#stopBtn {
            background-color: #4a2b2b;
            border: 1px solid #e05252;
            color: #e05252;
            font-weight: bold;
        }
        QPushButton#stopBtn:hover {
            background-color: #6a3b3b;
        }
        QFrame#phaseFrame {
            background-color: #2b2d30;
            border-radius: 8px;
            border: 2px solid #3d3f43;
        }
        QStatusBar {
            background-color: #1e1e2e;
            border-top: 1px solid #3d3f43;
        }
        """
        self.setStyleSheet(qss)

    def _update_ui_state(self):
        """UI 상태에 따른 위젯 활성화/비활성화 업데이트"""
        if self.current_state == self.STATE_DISCONNECTED:
            self.port_combo.setEnabled(True)
            self.refresh_btn.setEnabled(True)
            self.connect_btn.setText("연결")
            self.connect_btn.setStyleSheet("")
            
            self.muscle_combo.setEnabled(False)
            self.motion_combo.setEnabled(False)
            self.trial_spin.setEnabled(False)
            self.browse_btn.setEnabled(False)
            
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
            self.reset_btn.setEnabled(True)
            
        elif self.current_state == self.STATE_CONNECTED:
            self.port_combo.setEnabled(False)
            self.refresh_btn.setEnabled(False)
            self.connect_btn.setText("연결 해제")
            self.connect_btn.setStyleSheet("color: #e05252;")
            
            self.muscle_combo.setEnabled(True)
            self.motion_combo.setEnabled(True)
            self.trial_spin.setEnabled(True)
            self.browse_btn.setEnabled(True)
            
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.reset_btn.setEnabled(True)
            
        elif self.current_state == self.STATE_RECORDING:
            self.port_combo.setEnabled(False)
            self.refresh_btn.setEnabled(False)
            self.connect_btn.setEnabled(False)
            
            self.muscle_combo.setEnabled(False)
            self.motion_combo.setEnabled(False)
            self.trial_spin.setEnabled(False)
            self.browse_btn.setEnabled(False)
            
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.reset_btn.setEnabled(False)
            
        elif self.current_state == self.STATE_ANALYZING:
            self.connect_btn.setEnabled(False)
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
            self.reset_btn.setEnabled(False)

    def _refresh_ports(self):
        """이용 가능한 COM 포트 새로고침"""
        current_port = self.port_combo.currentText()
        self.port_combo.clear()
        ports = self.serial_manager.get_available_ports()
        if ports:
            self.port_combo.addItems(ports)
            if current_port in ports:
                self.port_combo.setCurrentText(current_port)
        else:
            self.port_combo.addItem("포트 없음")

    def _browse_save_dir(self):
        """저장 경로 선택 다이얼로그"""
        dir_path = QFileDialog.getExistingDirectory(self, "저장 경로 선택", self.save_dir_edit.text())
        if dir_path:
            self.save_dir_edit.setText(dir_path)
            self.config.save_dir = Path(dir_path)

    @Slot()
    def _on_connect_clicked(self):
        """연결/연결해제 버튼 클릭 처리"""
        if self.current_state == self.STATE_DISCONNECTED:
            port = self.port_combo.currentText()
            if port and port != "포트 없음":
                self.serial_manager.connect(port)
        else:
            self.serial_manager.disconnect()

    @Slot(bool)
    def _on_connection_changed(self, connected):
        """시리얼 연결 상태 변경 처리"""
        if connected:
            self.current_state = self.STATE_CONNECTED
            self.status_conn_indicator.setText("● 연결됨")
            self.status_conn_indicator.setStyleSheet("color: #4ec54e;")
            self.status_bar.showMessage("기기에 연결되었습니다.", 3000)
        else:
            self.current_state = self.STATE_DISCONNECTED
            self.status_conn_indicator.setText("● 분리됨")
            self.status_conn_indicator.setStyleSheet("color: #e05252;")
            self.status_bar.showMessage("기기와 연결이 해제되었습니다.", 3000)
            self.connect_btn.setEnabled(True)
        self._update_ui_state()

    @Slot(str)
    def _on_error(self, message):
        """에러 메시지 처리"""
        QMessageBox.critical(self, "오류", message)
        self.status_bar.showMessage(f"오류: {message}")

    @Slot()
    def _on_start_recording(self):
        """기록 시작 처리"""
        muscle = self.muscle_combo.currentText()
        motion = self.motion_combo.currentText()
        trial = self.trial_spin.value()
        save_dir = Path(self.save_dir_edit.text())
        
        if muscle == 'Custom' or motion == 'Custom':
            QMessageBox.warning(self, "경고", "Custom 이름을 입력하세요.")
            return

        # Initialize recorder (RELAX_PRE에서 실제 기록 시작)
        self.recorder = DataRecorder(muscle, motion, trial, str(save_dir))
        self._recording_active = False
        
        # Start timer (카운트다운부터 시작)
        self.experiment_timer.start(motion)
        
        self.current_state = self.STATE_RECORDING
        self._update_ui_state()
        self.plot_widget.clear()

    @Slot()
    def _on_stop_recording(self):
        """기록 강제 중지 처리"""
        if self.experiment_timer.get_current_phase() != ExperimentPhase.IDLE.name:
            self.experiment_timer.stop()
        self._on_experiment_finished()

    @Slot()
    def _on_reset(self):
        """초기화 버튼 처리"""
        self.plot_widget.clear()
        if self.recorder:
            self.recorder.reset()
        self.phase_label.setText("준비")
        self.countdown_label.setText("")
        self.phase_frame.setStyleSheet("QFrame#phaseFrame { background-color: #2b2d30; }")

    @Slot(str)
    def _on_muscle_changed(self, text):
        """근육 선택 변경 시 Custom 처리"""
        if text == "Custom":
            custom_name = CustomInputDialog.get_text("사용자 지정 근육 입력", self)
            if custom_name:
                idx = self.muscle_combo.count() - 1
                self.muscle_combo.insertItem(idx, custom_name)
                self.muscle_combo.setCurrentIndex(idx)
            else:
                self.muscle_combo.setCurrentIndex(0)

    @Slot(str)
    def _on_motion_changed(self, text):
        """동작 선택 변경 시 Custom 처리"""
        if text == "Custom":
            custom_name = CustomInputDialog.get_text("사용자 지정 동작 입력", self)
            if custom_name:
                idx = self.motion_combo.count() - 1
                self.motion_combo.insertItem(idx, custom_name)
                self.motion_combo.setCurrentIndex(idx)
            else:
                self.motion_combo.setCurrentIndex(0)

    @Slot(int, int, int)
    def _on_data_received(self, raw, filtered, envelope):
        """시리얼 데이터 수신 처리"""
        self.sample_count += 1
        
        # Update plot
        self.plot_widget.add_data(raw, filtered, envelope)
        
        # Add to recorder if recording
        if self.current_state == self.STATE_RECORDING and self._recording_active and self.recorder and self.recorder.is_recording():
            label = self.recorder.get_current_label()
            self.recorder.add_data(raw, filtered, envelope, label)

    def _update_data_rate(self):
        """초당 데이터 수신율 업데이트"""
        self.current_rate = self.sample_count
        self.sample_count = 0
        self.status_rate_label.setText(f"{self.current_rate} 샘플/초")

    @Slot(str, str)
    def _on_phase_changed(self, phase_name, label):
        """실험 타이머 단계 변경 처리"""
        if self.current_state != self.STATE_RECORDING:
            return
            
        # Update recorder label
        if self.recorder:
            if phase_name == ExperimentPhase.COUNTDOWN.name:
                pass  # 카운트다운 동안은 기록하지 않음
            elif phase_name == ExperimentPhase.RELAX_PRE.name:
                # RELAX_PRE 단계에서 실제 데이터 기록 시작
                self.recorder.start_recording()
                self._recording_active = True
                self.recorder.set_label(label)
            else:
                self.recorder.set_label(label)
                
        # Update UI text
        display_text = ""
        bg_color = "#2b2d30"
        
        if phase_name == ExperimentPhase.COUNTDOWN.name:
            display_text = "준비 (카운트다운)"
            bg_color = "#8a6d2b" # 황색
        elif phase_name == ExperimentPhase.RELAX_PRE.name or phase_name == ExperimentPhase.RELAX_POST.name:
            display_text = f"이완: {label}"
            bg_color = "#2b5a3a" # 녹색
        elif phase_name == ExperimentPhase.MOTION.name:
            display_text = f"동작: {label}"
            bg_color = "#6a2b2b" # 붉은색
            
        self.phase_label.setText(display_text)
        self.phase_frame.setStyleSheet(f"QFrame#phaseFrame {{ background-color: {bg_color}; border-radius: 8px; border: 2px solid #3d3f43; }}")

    @Slot(float)
    def _on_countdown_tick(self, remaining):
        """카운트다운 틱 업데이트"""
        self.countdown_label.setText(f"{remaining:.1f}초")

    @Slot()
    def _on_experiment_finished(self):
        """실험 종료 처리"""
        if self.current_state != self.STATE_RECORDING:
            return
            
        self.current_state = self.STATE_ANALYZING
        self._update_ui_state()
        self.phase_label.setText("분석 중...")
        self.countdown_label.setText("")
        self.phase_frame.setStyleSheet("QFrame#phaseFrame { background-color: #2b4a5a; border-radius: 8px; }")
        
        # Stop recording and get data
        save_path = self.recorder.stop_recording()
        data = self.recorder.get_data()
        
        muscle = self.muscle_combo.currentText()
        motion = self.motion_combo.currentText()
        trial = self.trial_spin.value()
        trial_save_dir = self.recorder.get_save_path()
        
        # Run analysis in background thread using QThread (GUI Safe)
        self.analysis_thread = QThread()
        self.analysis_worker = AnalysisWorker(data, trial_save_dir, muscle, motion, trial)
        self.analysis_worker.moveToThread(self.analysis_thread)
        
        self.analysis_thread.started.connect(self.analysis_worker.run)
        self.analysis_worker.finished.connect(self._on_analysis_finished)
        self.analysis_worker.error.connect(self._on_analysis_error)
        
        # Memory cleanup
        self.analysis_worker.finished.connect(self.analysis_thread.quit)
        self.analysis_worker.finished.connect(self.analysis_worker.deleteLater)
        self.analysis_worker.error.connect(self.analysis_thread.quit)
        self.analysis_worker.error.connect(self.analysis_worker.deleteLater)
        self.analysis_thread.finished.connect(self.analysis_thread.deleteLater)
        
        self.analysis_thread.start()

    def _on_analysis_finished(self, stats, save_dir):
        """분석 완료 처리 (GUI 스레드)"""
        muscle = self.muscle_combo.currentText()
        motion = self.motion_combo.currentText()
        trial = self.trial_spin.value()
        
        self.current_state = self.STATE_CONNECTED
        self._update_ui_state()
        self.phase_label.setText("실험 완료")
        self.phase_frame.setStyleSheet("QFrame#phaseFrame { background-color: #2b2d30; }")
        
        # Auto-increment trial
        self.trial_spin.setValue(trial + 1)
        
        # Show results
        dialog = RecordingCompleteDialog(self, muscle, motion, trial, stats, save_dir)
        dialog.exec()

    def _on_analysis_error(self, err_msg):
        """분석 오류 처리 (GUI 스레드)"""
        self.current_state = self.STATE_CONNECTED
        self._update_ui_state()
        self.phase_label.setText("분석 오류")
        QMessageBox.critical(self, "분석 오류", f"데이터 분석 중 오류가 발생했습니다:\n{err_msg}")

    def closeEvent(self, event):
        """창 닫기 이벤트 처리"""
        if self.serial_manager.is_connected():
            self.serial_manager.disconnect()
        if self.experiment_timer:
            self.experiment_timer.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
