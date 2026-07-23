import os
import sys
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QLineEdit, QPushButton, QGroupBox, QFormLayout)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

# 로깅 설정
logger = logging.getLogger(__name__)

# 공통 QSS 스타일
DIALOG_STYLE = """
QDialog {
    background-color: #2b2d30;
    color: #e0e0e0;
}
QLabel {
    color: #e0e0e0;
}
QGroupBox {
    color: #e0e0e0;
    border: 1px solid #555555;
    border-radius: 5px;
    margin-top: 1ex;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top center;
    padding: 0 3px;
}
QLineEdit {
    background-color: #3b3d40;
    color: #e0e0e0;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 4px;
}
QPushButton {
    background-color: #4a5056;
    color: #e0e0e0;
    border: none;
    border-radius: 4px;
    padding: 6px 12px;
}
QPushButton:hover {
    background-color: #5a6066;
}
QPushButton:pressed {
    background-color: #3a4046;
}
QPushButton#AccentButton {
    background-color: #4a9eff;
    color: #ffffff;
    font-weight: bold;
}
QPushButton#AccentButton:hover {
    background-color: #5ab0ff;
}
QPushButton#AccentButton:pressed {
    background-color: #3a8eef;
}
QPushButton:disabled {
    background-color: #3a3d40;
    color: #777777;
}
"""

class CustomInputDialog(QDialog):
    """
    사용자 정의 근육 또는 동작 이름을 입력받기 위한 다이얼로그 클래스입니다.
    """

    def __init__(self, title: str, parent=None) -> None:
        """
        CustomInputDialog를 초기화합니다.

        Args:
            title (str): 다이얼로그의 제목.
            parent: 부모 위젯.
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet(DIALOG_STYLE)
        self.resize(300, 100)

        # UI 설정
        layout = QVBoxLayout(self)

        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("이름을 입력하세요")
        self.input_field.textChanged.connect(self._validate_input)
        layout.addWidget(self.input_field)

        button_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("취소", self)
        self.btn_ok = QPushButton("확인", self)
        self.btn_ok.setObjectName("AccentButton")
        self.btn_ok.setEnabled(False) # 처음에는 비활성화 (빈 문자열 방지)

        button_layout.addStretch()
        button_layout.addWidget(self.btn_cancel)
        button_layout.addWidget(self.btn_ok)

        layout.addLayout(button_layout)

        # 시그널 연결
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self.accept)

    def _validate_input(self, text: str) -> None:
        """
        입력된 텍스트가 유효한지(비어있지 않은지) 검증하고 확인 버튼 상태를 업데이트합니다.

        Args:
            text (str): 입력된 텍스트.
        """
        self.btn_ok.setEnabled(bool(text.strip()))

    @staticmethod
    def get_text(title: str, parent=None) -> Optional[str]:
        """
        다이얼로그를 띄우고 사용자가 입력한 텍스트를 반환합니다.

        Args:
            title (str): 다이얼로그의 제목.
            parent: 부모 위젯.

        Returns:
            Optional[str]: 사용자가 확인을 누르면 입력한 문자열을, 취소하면 None을 반환합니다.
        """
        dialog = CustomInputDialog(title, parent)
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            return dialog.input_field.text().strip()
        return None


class RecordingCompleteDialog(QDialog):
    """
    기록이 완료된 후 결과를 요약하여 보여주는 다이얼로그 클래스입니다.
    """

    def __init__(self, parent, muscle: str, motion: str, trial: int, stats: Dict[str, Dict[str, float]], save_path: Path) -> None:
        """
        RecordingCompleteDialog를 초기화합니다.

        Args:
            parent: 부모 위젯.
            muscle (str): 측정한 근육 이름.
            motion (str): 측정한 동작 이름.
            trial (int): 시도 횟수(회차).
            stats (Dict[str, Dict[str, float]]): 상태별 통계값 딕셔너리. (키: 'overall', 'relax', 'motion')
            save_path (Path): 데이터가 저장된 디렉토리 경로.
        """
        super().__init__(parent)
        self.setWindowTitle("기록 완료")
        self.setStyleSheet(DIALOG_STYLE)
        self.resize(450, 350)
        self.save_path = save_path

        layout = QVBoxLayout(self)

        # 1. 요약 정보 그룹
        summary_group = QGroupBox("요약 정보")
        summary_layout = QFormLayout()
        summary_layout.addRow("근육 (Muscle):", QLabel(muscle))
        summary_layout.addRow("동작 (Motion):", QLabel(motion))
        summary_layout.addRow("회차 (Trial):", QLabel(f"{trial}회"))
        summary_group.setLayout(summary_layout)
        layout.addWidget(summary_group)

        # 2. 통계 정보 그룹
        stats_group = QGroupBox("통계 (Statistics)")
        stats_layout = QVBoxLayout()
        
        # 고정폭 폰트 설정 (통계 정렬용)
        mono_font = QFont("Consolas", 10)
        mono_font.setStyleHint(QFont.StyleHint.Monospace)

        # Relax 통계 (analyzer.py는 소문자 키 사용)
        if "relax" in stats:
            relax_stats = stats["relax"]
            relax_label = QLabel(self._format_stats("휴식 (Relax)", relax_stats))
            relax_label.setFont(mono_font)
            stats_layout.addWidget(relax_label)

        # Motion 통계
        if "motion" in stats:
            motion_stats = stats["motion"]
            motion_label = QLabel(self._format_stats("동작 (Motion)", motion_stats))
            motion_label.setFont(mono_font)
            stats_layout.addWidget(motion_label)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # 3. 저장 위치 및 버튼 그룹
        path_group = QGroupBox("저장 위치")
        path_layout = QVBoxLayout()
        path_label = QLabel(str(self.save_path))
        path_label.setWordWrap(True)
        path_layout.addWidget(path_label)
        path_group.setLayout(path_layout)
        layout.addWidget(path_group)

        # 하단 버튼
        button_layout = QHBoxLayout()
        self.btn_open_folder = QPushButton("폴더 열기", self)
        self.btn_ok = QPushButton("확인", self)
        self.btn_ok.setObjectName("AccentButton")

        button_layout.addStretch()
        button_layout.addWidget(self.btn_open_folder)
        button_layout.addWidget(self.btn_ok)

        layout.addLayout(button_layout)

        # 시그널 연결
        self.btn_open_folder.clicked.connect(self._open_save_folder)
        self.btn_ok.clicked.connect(self.accept)

    def _format_stats(self, phase_name: str, stats: Dict[str, float]) -> str:
        """
        통계 딕셔너리를 정렬된 문자열로 포맷팅합니다.

        Args:
            phase_name (str): 단계 이름 ('휴식' 또는 '동작').
            stats (Dict[str, float]): 통계값 딕셔너리.

        Returns:
            str: 포맷팅된 문자열.
        """
        mean_val = stats.get('Mean', 0.0)
        max_val = stats.get('Max', 0.0)
        min_val = stats.get('Min', 0.0)
        rms_val = stats.get('RMS', 0.0)

        return (f"[{phase_name}]\n"
                f"  Mean: {mean_val:8.2f}  |  Max: {max_val:8.2f}\n"
                f"  Min : {min_val:8.2f}  |  RMS: {rms_val:8.2f}")

    def _open_save_folder(self) -> None:
        """
        저장된 파일이 있는 폴더를 파일 탐색기에서 엽니다.
        """
        folder_path = self.save_path.parent
        if not folder_path.exists():
            logger.warning(f"폴더가 존재하지 않습니다: {folder_path}")
            return

        try:
            if os.name == 'nt': # Windows
                os.startfile(folder_path)
            elif sys.platform == 'darwin': # macOS
                subprocess.Popen(['open', str(folder_path)])
            else: # Linux
                subprocess.Popen(['xdg-open', str(folder_path)])
            logger.info(f"폴더를 열었습니다: {folder_path}")
        except Exception as e:
            logger.error(f"폴더를 여는 중 오류 발생: {e}")
