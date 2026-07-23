"""
EMG Data Collector - 메인 진입점
아두이노 기반 표면 근전도(sEMG) 데이터 수집 애플리케이션
"""
import sys
import logging
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from gui.main_window import MainWindow

def setup_logging() -> None:
    """로깅 시스템을 초기화합니다."""
    log_dir = project_root / 'logs'
    log_dir.mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / 'emg_collector.log', encoding='utf-8')
        ]
    )

def main() -> None:
    """애플리케이션을 시작합니다."""
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info('EMG Data Collector 시작')
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # 모든 OS에서 일관된 모양
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
