import sys
import os
import logging
from pathlib import Path
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                                QLabel, QComboBox, QPushButton, QSpinBox,
                                QLineEdit, QGroupBox, QFrame, QStatusBar,
                                QFileDialog, QMessageBox, QApplication)
from PySide6.QtCore import Qt, QTimer, Slot, Signal, QObject, QThread
from PySide6.QtGui import QFont, QColor

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.config import AppConfig, MUSCLES, MOTIONS, LABEL_RELAX, LABEL_TRANSITION, APP_TITLE, ExperimentPhase
from utils.timer import ExperimentTimer
from graphs.realtime_plot import RealtimePlot
from gui.dialogs import CustomInputDialog, RecordingCompleteDialog
from recorder.recorder import DataRecorder
from analysis.analyzer import EMGAnalyzer
from analysis.multi_trial_analyzer import MultiTrialAnalyzer

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


class ReportWorker(QObject):
    """백그라운드에서 Multi-Trial Report를 생성하기 위한 워커 클래스"""
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, muscle, base_dir):
        super().__init__()
        self.muscle = muscle
        self.base_dir = base_dir

    def run(self):
        try:
            mta = MultiTrialAnalyzer(self.muscle, self.base_dir)
            if mta.get_trial_count() == 0:
                self.error.emit("No trials found to generate report.")
                return
            result_paths = mta.run_all()
            self.finished.emit(list(result_paths.values()))
        except Exception as e:
            logging.error(f"Report 생성 중 오류 발생: {e}")
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
        conn_group = QGroupBox("Connection")
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
        
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        
        conn_layout.addLayout(port_layout)
        conn_layout.addWidget(self.connect_btn)
        conn_group.setLayout(conn_layout)

        # 2. Experiment Section
        exp_group = QGroupBox("Experiment")
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
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self._browse_save_dir)
        save_layout.addWidget(self.save_dir_edit)
        save_layout.addWidget(self.browse_btn)

        exp_layout.addWidget(QLabel("Muscle:"))
        exp_layout.addWidget(self.muscle_combo)
        exp_layout.addWidget(QLabel("Motion:"))
        exp_layout.addWidget(self.motion_combo)
        exp_layout.addWidget(QLabel("Trial:"))
        exp_layout.addWidget(self.trial_spin)
        exp_layout.addWidget(QLabel("Save Path:"))
        exp_layout.addLayout(save_layout)
        exp_group.setLayout(exp_layout)

        # 3. Control Section
        ctrl_group = QGroupBox("Control")
        ctrl_layout = QVBoxLayout()
        
        self.start_btn = QPushButton("Start Recording")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.clicked.connect(self._on_start_recording)
        
        self.stop_btn = QPushButton("Stop Recording")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.clicked.connect(self._on_stop_recording)
        
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setMinimumHeight(30)
        self.reset_btn.clicked.connect(self._on_reset)
        
        ctrl_layout.addWidget(self.start_btn)
        ctrl_layout.addWidget(self.stop_btn)
        ctrl_layout.addWidget(self.reset_btn)
        ctrl_group.setLayout(ctrl_layout)

        # 4. Multi-Trial Report Section
        report_group = QGroupBox("Report")
        report_layout = QVBoxLayout()

        self.report_btn = QPushButton("Generate Multi-Trial Report")
        self.report_btn.setObjectName("reportBtn")
        self.report_btn.setMinimumHeight(35)
        self.report_btn.clicked.connect(self._on_generate_report)
        self.report_btn.setEnabled(False)

        self.trial_progress_label = QLabel("No trials recorded yet")
        self.trial_progress_label.setStyleSheet("color: #999; font-size: 11px;")

        report_layout.addWidget(self.report_btn)
        report_layout.addWidget(self.trial_progress_label)
        report_group.setLayout(report_layout)

        left_layout.addWidget(conn_group)
        left_layout.addWidget(exp_group)
        left_layout.addWidget(ctrl_group)
        left_layout.addWidget(report_group)
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
        
        self.phase_label = QLabel("Ready")
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
        
        self.status_conn_indicator = QLabel("● Disconnected")
        self.status_conn_indicator.setStyleSheet("color: #e05252;")
        self.status_rate_label = QLabel("0 samples/s")
        
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
        QPushButton#reportBtn {
            background-color: #2b3a5a;
            border: 1px solid #4a9eff;
            color: #4a9eff;
            font-weight: bold;
        }
        QPushButton#reportBtn:hover {
            background-color: #3b4a6a;
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
            self.connect_btn.setText("Connect")
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
            self.connect_btn.setText("Disconnect")
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
            self.port_combo.addItem("No ports found")

    def _browse_save_dir(self):
        """저장 경로 선택 다이얼로그"""
        dir_path = QFileDialog.getExistingDirectory(self, "Select Save Directory", self.save_dir_edit.text())
        if dir_path:
            self.save_dir_edit.setText(dir_path)
            self.config.save_dir = Path(dir_path)

    @Slot()
    def _on_connect_clicked(self):
        """연결/연결해제 버튼 클릭 처리"""
        if self.current_state == self.STATE_DISCONNECTED:
            port = self.port_combo.currentText()
            if port and port != "No ports found":
                self.serial_manager.connect(port)
        else:
            self.serial_manager.disconnect()

    @Slot(bool)
    def _on_connection_changed(self, connected):
        """시리얼 연결 상태 변경 처리"""
        if connected:
            self.current_state = self.STATE_CONNECTED
            self.status_conn_indicator.setText("● Connected")
            self.status_conn_indicator.setStyleSheet("color: #4ec54e;")
            self.status_bar.showMessage("Device connected.", 3000)
        else:
            self.current_state = self.STATE_DISCONNECTED
            self.status_conn_indicator.setText("● Disconnected")
            self.status_conn_indicator.setStyleSheet("color: #e05252;")
            self.status_bar.showMessage("Device disconnected.", 3000)
            self.connect_btn.setEnabled(True)
        self._update_ui_state()

    @Slot(str)
    def _on_error(self, message):
        """에러 메시지 처리"""
        QMessageBox.critical(self, "Error", message)
        self.status_bar.showMessage(f"Error: {message}")

    @Slot()
    def _on_start_recording(self):
        """기록 시작 처리"""
        muscle = self.muscle_combo.currentText()
        motion = self.motion_combo.currentText()
        trial = self.trial_spin.value()
        save_dir = Path(self.save_dir_edit.text())
        
        if muscle == 'Custom' or motion == 'Custom':
            QMessageBox.warning(self, "Warning", "Please enter a custom name first.")
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
        self.phase_label.setText("Ready")
        self.countdown_label.setText("")
        self.phase_frame.setStyleSheet("QFrame#phaseFrame { background-color: #2b2d30; }")

    @Slot(str)
    def _on_muscle_changed(self, text):
        """근육 선택 변경 시 Custom 처리"""
        if text == "Custom":
            custom_name = CustomInputDialog.get_text("Enter Custom Muscle Name", self)
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
            custom_name = CustomInputDialog.get_text("Enter Custom Motion Name", self)
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
        self.status_rate_label.setText(f"{self.current_rate} samples/s")

    @Slot(str, str)
    def _on_phase_changed(self, phase_name, label):
        """실험 타이머 단계 변경 처리"""
        if self.current_state != self.STATE_RECORDING:
            return
            
        # Update recorder label
        if self.recorder:
            if phase_name == ExperimentPhase.COUNTDOWN.name:
                pass  # Don't record during countdown
            elif phase_name == ExperimentPhase.RELAX_PRE.name:
                # Start actual data recording at RELAX_PRE
                self.recorder.start_recording()
                self._recording_active = True
                self.recorder.set_label(label)
            elif phase_name in (ExperimentPhase.TRANSITION_1.name, ExperimentPhase.TRANSITION_2.name):
                self.recorder.set_label(LABEL_TRANSITION)
            else:
                self.recorder.set_label(label)
                
        # Update UI text
        display_text = ""
        bg_color = "#2b2d30"
        
        if phase_name == ExperimentPhase.COUNTDOWN.name:
            display_text = "Get Ready"
            bg_color = "#8a6d2b"
        elif phase_name == ExperimentPhase.RELAX_PRE.name or phase_name == ExperimentPhase.RELAX_POST.name:
            display_text = "Relax"
            bg_color = "#2b5a3a"
        elif phase_name == ExperimentPhase.TRANSITION_1.name or phase_name == ExperimentPhase.TRANSITION_2.name:
            display_text = "Transition"
            bg_color = "#5a5a2b"
        elif phase_name == ExperimentPhase.MOTION.name:
            display_text = f"{label}"
            bg_color = "#6a2b2b"
            
        self.phase_label.setText(display_text)
        self.phase_frame.setStyleSheet(f"QFrame#phaseFrame {{ background-color: {bg_color}; border-radius: 8px; border: 2px solid #3d3f43; }}")

    @Slot(float)
    def _on_countdown_tick(self, remaining):
        """카운트다운 틱 업데이트"""
        self.countdown_label.setText(f"{remaining:.1f}s")

    @Slot()
    def _on_experiment_finished(self):
        """실험 종료 처리"""
        if self.current_state != self.STATE_RECORDING:
            return
            
        self.current_state = self.STATE_ANALYZING
        self._update_ui_state()
        self.phase_label.setText("Analyzing...")
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
        self.phase_label.setText("Complete")
        self.phase_frame.setStyleSheet("QFrame#phaseFrame { background-color: #2b2d30; }")
        
        # Auto-increment trial
        self.trial_spin.setValue(trial + 1)

        # Update trial progress
        self._update_trial_progress()

        # Show results
        dialog = RecordingCompleteDialog(self, muscle, motion, trial, stats, save_dir)
        dialog.exec()

    def _on_analysis_error(self, err_msg):
        """분석 오류 처리 (GUI 스레드)"""
        self.current_state = self.STATE_CONNECTED
        self._update_ui_state()
        self.phase_label.setText("Analysis Error")
        QMessageBox.critical(self, "Analysis Error", f"An error occurred during data analysis:\n{err_msg}")

    def _update_trial_progress(self):
        """Trial 진행 현황을 업데이트하고 Report 버튼 활성화 여부를 결정합니다."""
        muscle = self.muscle_combo.currentText()
        if muscle == 'Custom':
            return

        save_dir = Path(self.save_dir_edit.text())
        try:
            mta = MultiTrialAnalyzer(muscle, save_dir)
            count = mta.get_trial_count()
            motions = mta.get_available_motions()

            if count > 0:
                motion_str = ", ".join(motions) if motions else "N/A"
                self.trial_progress_label.setText(
                    f"{count} trial(s) found | Motions: {motion_str}"
                )
                self.trial_progress_label.setStyleSheet("color: #4ec54e; font-size: 11px;")
                self.report_btn.setEnabled(True)
            else:
                self.trial_progress_label.setText("No trials recorded yet")
                self.trial_progress_label.setStyleSheet("color: #999; font-size: 11px;")
                self.report_btn.setEnabled(False)
        except Exception as e:
            logging.warning(f"Failed to update trial progress: {e}")

    @Slot()
    def _on_generate_report(self):
        """Multi-Trial Report 생성 (백그라운드 QThread)"""
        muscle = self.muscle_combo.currentText()
        save_dir = Path(self.save_dir_edit.text())

        self.report_btn.setEnabled(False)
        self.report_btn.setText("Generating...")
        self.status_bar.showMessage("Generating multi-trial report...", 0)

        # Report를 백그라운드에서 생성
        self.report_thread = QThread()
        self.report_worker = ReportWorker(muscle, save_dir)
        self.report_worker.moveToThread(self.report_thread)

        self.report_thread.started.connect(self.report_worker.run)
        self.report_worker.finished.connect(self._on_report_finished)
        self.report_worker.error.connect(self._on_report_error)

        self.report_worker.finished.connect(self.report_thread.quit)
        self.report_worker.finished.connect(self.report_worker.deleteLater)
        self.report_worker.error.connect(self.report_thread.quit)
        self.report_worker.error.connect(self.report_worker.deleteLater)
        self.report_thread.finished.connect(self.report_thread.deleteLater)

        self.report_thread.start()

    def _on_report_finished(self, result_paths):
        """Report 생성 완료 처리"""
        self.report_btn.setText("Generate Multi-Trial Report")
        self.report_btn.setEnabled(True)

        file_list = "\n".join([f"  • {p}" for p in result_paths])
        self.status_bar.showMessage("Multi-trial report generated successfully!", 5000)
        QMessageBox.information(
            self,
            "Report Generated",
            f"Multi-trial report generated successfully!\n\nFiles created:\n{file_list}"
        )

    def _on_report_error(self, err_msg):
        """Report 생성 오류 처리"""
        self.report_btn.setText("Generate Multi-Trial Report")
        self.report_btn.setEnabled(True)
        self.status_bar.showMessage("Report generation failed.", 5000)
        QMessageBox.critical(self, "Report Error", f"Failed to generate report:\n{err_msg}")

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
