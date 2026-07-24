import serial
import serial.tools.list_ports
from PySide6.QtCore import QObject, QThread, Signal, Slot
import logging
import time
from typing import List, Optional

logger = logging.getLogger(__name__)

class SerialWorker(QObject):
    """
    시리얼 통신을 담당하는 워커 클래스.
    QThread 환경에서 실행되며 지속적으로 데이터를 읽어 처리합니다.
    """
    data_received = Signal(int, int, int)
    error_occurred = Signal(str)
    finished = Signal()

    def __init__(self, serial_port: serial.Serial) -> None:
        super().__init__()
        self._serial = serial_port
        self._is_running = False

    @Slot()
    def run(self) -> None:
        """
        워커 스레드의 메인 루프.
        시리얼 데이터를 읽어들이고 파싱하여 시그널로 전달합니다.
        """
        self._is_running = True
        
        # 아두이노 리셋 시 발생할 수 있는 초기 쓰레기 데이터 무시
        discard_count = 5
        
        while self._is_running:
            try:
                if not self._serial.is_open:
                    break
                    
                line = self._serial.readline()
                
                if not line:
                    continue
                    
                if discard_count > 0:
                    discard_count -= 1
                    continue
                    
                try:
                    decoded_line = line.decode('utf-8').strip()
                except UnicodeDecodeError:
                    logger.warning("Decode error: invalid character received")
                    continue
                
                if not decoded_line:
                    continue
                    
                # 데이터 포맷: Raw,Filtered,Envelope
                parts = decoded_line.split(',')
                if len(parts) == 3:
                    try:
                        raw = int(parts[0])
                        filtered = int(parts[1])
                        envelope = int(parts[2])
                        self.data_received.emit(raw, filtered, envelope)
                    except ValueError:
                        logger.warning(f"Data conversion error (non-numeric): {decoded_line}")
                else:
                    logger.warning(f"Data format error (unexpected field count): {decoded_line}")
                    
            except serial.SerialException as e:
                logger.error(f"Serial communication error: {e}")
                self.error_occurred.emit(f"Connection lost: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                self.error_occurred.emit(f"Unknown error: {e}")
                break

        self.finished.emit()

    def stop(self) -> None:
        """워커 스레드의 실행을 중지합니다."""
        self._is_running = False


class SerialManager(QObject):
    """
    아두이노와의 시리얼 통신을 관리하는 매니저 클래스.
    스레드의 생명주기 관리 및 연결 상태를 제어합니다.
    """
    data_received = Signal(int, int, int)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._serial: Optional[serial.Serial] = None
        self._worker: Optional[SerialWorker] = None
        self._thread: Optional[QThread] = None

    def get_available_ports(self) -> List[str]:
        """
        현재 시스템에서 사용 가능한 시리얼 포트 목록을 반환합니다.
        
        Returns:
            List[str]: 포트 이름 목록 (예: ['COM1', 'COM2'])
        """
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

    def connect(self, port: str, baud_rate: int = 115200) -> bool:
        """
        주어진 포트와 보드레이트로 시리얼 통신 연결을 시도합니다.
        
        Args:
            port (str): 연결할 포트 이름 (예: 'COM3')
            baud_rate (int): 통신 속도 (기본값: 115200)
            
        Returns:
            bool: 연결 성공 여부
        """
        if self.is_connected():
            self.disconnect()

        try:
            # 타임아웃을 설정하여 readline()이 무한 대기하지 않도록 함
            self._serial = serial.Serial(
                port=port,
                baudrate=baud_rate,
                timeout=1.0,
                write_timeout=1.0
            )
            
            self._thread = QThread()
            self._worker = SerialWorker(self._serial)
            self._worker.moveToThread(self._thread)
            
            # 스레드 시작 및 종료 시그널 연결
            self._thread.started.connect(self._worker.run)
            self._worker.finished.connect(self._thread.quit)
            self._worker.finished.connect(self._worker.deleteLater)
            self._thread.finished.connect(self._thread.deleteLater)
            
            # 데이터 수신 및 에러 시그널 연결
            self._worker.data_received.connect(self.data_received)
            self._worker.error_occurred.connect(self._handle_worker_error)
            
            self._thread.start()
            self.connection_changed.emit(True)
            logger.info(f"Serial port connected: {port} @ {baud_rate}bps")
            return True
            
        except serial.SerialException as e:
            error_msg = f"Port connection failed ({port}): {e}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            self._serial = None
            return False

    def disconnect(self) -> None:
        """
        현재 시리얼 연결을 안전하게 해제하고 워커 스레드를 종료합니다.
        """
        if self._worker:
            self._worker.stop()
            
        if self._thread:
            self._thread.quit()
            self._thread.wait()
            self._worker = None
            self._thread = None
            
        if self._serial and self._serial.is_open:
            try:
                # 남아있는 버퍼 클리어 시도
                if hasattr(self._serial, 'cancel_read'):
                    self._serial.cancel_read()
                if hasattr(self._serial, 'cancel_write'):
                    self._serial.cancel_write()
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()
            except Exception as e:
                logger.warning(f"Failed to flush buffers: {e}")
                
            self._serial.close()
            self._serial = None
            self.connection_changed.emit(False)
            logger.info("Serial connection closed")

    def is_connected(self) -> bool:
        """
        현재 시리얼 통신이 연결되어 있는지 여부를 반환합니다.
        
        Returns:
            bool: 연결 여부
        """
        return self._serial is not None and self._serial.is_open

    @Slot(str)
    def _handle_worker_error(self, error_msg: str) -> None:
        """
        워커에서 발생한 에러를 처리하고 연결을 종료합니다.
        
        Args:
            error_msg (str): 발생한 에러 메시지
        """
        logger.error(f"Worker thread error detected: {error_msg}")
        self.error_occurred.emit(error_msg)
        self.disconnect()
