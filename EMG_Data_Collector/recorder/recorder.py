"""
EMG 데이터를 기록하고 저장하는 모듈.
"""

import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

import pandas as pd

logger = logging.getLogger(__name__)

class DataRecorder:
    """
    실험 중 EMG 데이터를 기록하기 위한 클래스.
    """

    def __init__(self, muscle: str, motion: str, trial: int, save_dir: str = 'Data'):
        """
        DataRecorder 인스턴스를 초기화합니다.

        Args:
            muscle (str): 측정 근육의 이름 (예: 'FCU').
            motion (str): 수행 중인 동작의 이름 (예: 'Fist').
            trial (int): 현재 시도 횟수.
            save_dir (str): 데이터를 저장할 최상위 디렉토리. 기본값은 'Data'.
        """
        self.muscle = muscle
        self.motion = motion
        self.trial = trial
        self.save_dir = Path(save_dir)
        
        self._data: List[Dict[str, Any]] = []
        self._is_recording = False
        self._start_time: Optional[float] = None
        self._current_label = "Relax"

    def start_recording(self) -> None:
        """
        데이터 기록을 시작합니다.
        기록 상태를 활성화하고 시작 시간을 설정합니다.
        """
        self.reset()
        self._start_time = time.perf_counter()
        self._is_recording = True
        logger.info(f"데이터 기록을 시작합니다: 근육={self.muscle}, 동작={self.motion}, 시도={self.trial}")

    def add_data(self, raw: int, filtered: int, envelope: int, label: str) -> None:
        """
        새로운 데이터 포인트를 추가합니다.

        Args:
            raw (int): 원본 EMG 데이터.
            filtered (int): 필터링된 EMG 데이터.
            envelope (int): 엔벨로프(포락선) 데이터.
            label (str): 현재 라벨 (예: 'Relax', 'Contraction').
        """
        if not self._is_recording or self._start_time is None:
            return

        current_time = time.perf_counter()
        elapsed_time = round(current_time - self._start_time, 4)

        data_point = {
            'Time': elapsed_time,
            'Raw': raw,
            'Filtered': filtered,
            'Envelope': envelope,
            'Muscle': self.muscle,
            'Motion': self.motion,
            'Label': label,
            'Trial': self.trial
        }
        self._data.append(data_point)

    def stop_recording(self) -> Path:
        """
        데이터 기록을 중지하고 CSV 파일로 저장합니다.

        Returns:
            Path: 저장된 CSV 파일의 경로.
        """
        self._is_recording = False
        logger.info("데이터 기록을 중지했습니다.")
        
        if not self._data:
            logger.warning("기록된 데이터가 없습니다.")

        df = pd.DataFrame(self._data)
        
        # 지정된 컬럼 순서를 보장
        columns = ['Time', 'Raw', 'Filtered', 'Envelope', 'Muscle', 'Motion', 'Label', 'Trial']
        if not df.empty:
            df = df[columns]
        else:
            df = pd.DataFrame(columns=columns)

        save_path = self.get_save_path()
        save_path.mkdir(parents=True, exist_ok=True)

        trial_str = f"Trial{self.trial:03d}"
        file_name = f"{self.muscle}_{self.motion}_{trial_str}.csv"
        file_path = save_path / file_name

        df.to_csv(file_path, index=False)
        logger.info(f"총 {len(self._data)}개의 데이터 포인트를 {file_path}에 저장했습니다.")

        return file_path

    def set_label(self, label: str) -> None:
        """
        현재 기록 중인 데이터의 라벨을 설정합니다.

        Args:
            label (str): 새로운 라벨 값.
        """
        self._current_label = label

    def get_current_label(self) -> str:
        """
        현재 라벨을 반환합니다.

        Returns:
            str: 현재 설정된 라벨.
        """
        return self._current_label

    def get_data(self) -> pd.DataFrame:
        """
        현재까지 기록된 데이터의 복사본을 DataFrame 형태로 반환합니다.

        Returns:
            pd.DataFrame: 기록된 데이터.
        """
        df = pd.DataFrame(self._data)
        columns = ['Time', 'Raw', 'Filtered', 'Envelope', 'Muscle', 'Motion', 'Label', 'Trial']
        if not df.empty:
            return df[columns]
        return pd.DataFrame(columns=columns)

    def get_save_path(self) -> Path:
        """
        데이터가 저장될 디렉토리 경로를 반환합니다.

        Returns:
            Path: 저장될 디렉토리 경로.
        """
        trial_str = f"Trial{self.trial:03d}"
        return self.save_dir / self.muscle / trial_str

    def is_recording(self) -> bool:
        """
        현재 기록 중인지 여부를 반환합니다.

        Returns:
            bool: 기록 중이면 True, 그렇지 않으면 False.
        """
        return self._is_recording

    def reset(self) -> None:
        """
        기록된 모든 데이터를 초기화합니다.
        """
        self._data.clear()
        self._start_time = None
        self._is_recording = False
