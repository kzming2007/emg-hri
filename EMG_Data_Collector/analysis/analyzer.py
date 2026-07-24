"""
sEMG 데이터의 통계적 분석 및 그래프 생성을 담당하는 모듈입니다.
Transition 구간 제외, Smoothed Envelope 오버레이, Sliding Window RMS를 지원합니다.
"""
import logging
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import matplotlib
# GUI 스레드 충돌을 방지하기 위해 백엔드를 'Agg'로 설정합니다.
matplotlib.use('Agg')
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)


def _sliding_window_rms(data: np.ndarray, window_ms: int = 200, sample_rate: int = 1000) -> np.ndarray:
    """간단한 슬라이딩 윈도우 RMS (signal_processing 모듈 로드 실패 시 폴백)"""
    window_size = max(1, int(window_ms * sample_rate / 1000))
    squared = data.astype(np.float64) ** 2
    kernel = np.ones(window_size) / window_size
    mean_sq = np.convolve(squared, kernel, mode='same')
    return np.sqrt(mean_sq)


def _smooth_envelope(data: np.ndarray, window_ms: int = 50, sample_rate: int = 1000) -> np.ndarray:
    """간단한 Moving Average 스무딩 (signal_processing 모듈 로드 실패 시 폴백)"""
    window_size = max(1, int(window_ms * sample_rate / 1000))
    kernel = np.ones(window_size) / window_size
    return np.convolve(data, kernel, mode='same')


# signal_processing 모듈에서 고급 함수를 가져오기 시도
try:
    from analysis.signal_processing import EMGSignalProcessor
    _has_signal_processing = True
except ImportError:
    _has_signal_processing = False
    logger.warning("signal_processing module not available, using built-in fallbacks")


class EMGAnalyzer:
    """
    sEMG 데이터의 통계적 분석 및 그래프 생성을 담당하는 클래스입니다.
    Transition 라벨이 붙은 데이터를 통계에서 자동 제외합니다.
    """

    def __init__(self, data: pd.DataFrame, save_dir: Path, muscle: str, motion: str, trial: int):
        """
        EMGAnalyzer 초기화

        Args:
            data (pd.DataFrame): 분석할 sEMG 데이터프레임 (Time, Envelope, Label 컬럼 포함)
            save_dir (Path): 결과물을 저장할 디렉토리 경로
            muscle (str): 측정된 근육 이름
            motion (str): 수행한 동작 이름
            trial (int): 시도 횟수
        """
        self.data = data
        self.save_dir = Path(save_dir)
        self.muscle = muscle
        self.motion = motion
        self.trial = trial

        # 저장할 디렉토리가 없으면 생성
        self.save_dir.mkdir(parents=True, exist_ok=True)

        # 파일명 접두사
        self.file_prefix = f"{self.muscle}_{self.motion}_Trial{self.trial:03d}"

        # matplotlib 스타일 설정
        plt.style.use('seaborn-v0_8-whitegrid')

    def _filter_transitions(self, data: pd.DataFrame) -> pd.DataFrame:
        """Transition 라벨 행을 제외한 데이터프레임을 반환합니다."""
        if 'Label' in data.columns:
            return data[data['Label'] != 'Transition'].copy()
        return data.copy()

    def calculate_statistics(self, data: pd.DataFrame) -> dict:
        """
        주어진 데이터프레임의 Envelope 컬럼에 대한 통계값을 계산합니다.
        Transition 구간은 자동 제외됩니다.

        Args:
            data (pd.DataFrame): 분석할 데이터

        Returns:
            dict: 계산된 통계값 딕셔너리
        """
        # Transition 제외
        filtered = self._filter_transitions(data)

        if filtered.empty or 'Envelope' not in filtered.columns:
            return {
                'Mean': 0.0, 'Max': 0.0, 'Min': 0.0, 'Std': 0.0,
                'RMS': 0.0, 'MAV': 0.0, 'IEMG': 0.0
            }

        envelope = filtered['Envelope'].values.astype(np.float64)

        # 기본 통계량
        mean_val = np.mean(envelope)
        max_val = np.max(envelope)
        min_val = np.min(envelope)
        std_val = np.std(envelope)

        # RMS (Sliding Window 200ms의 평균값)
        if _has_signal_processing:
            rms_arr = EMGSignalProcessor.sliding_window_rms(envelope)
        else:
            rms_arr = _sliding_window_rms(envelope)
        rms = float(np.mean(rms_arr))

        # MAV (Mean Absolute Value)
        mav = np.mean(np.abs(envelope))

        # IEMG (Integrated EMG): dt = 1/sample_rate
        dt = 0.001
        iemg = np.sum(np.abs(envelope)) * dt

        return {
            'Mean': float(mean_val),
            'Max': float(max_val),
            'Min': float(min_val),
            'Std': float(std_val),
            'RMS': float(rms),
            'MAV': float(mav),
            'IEMG': float(iemg)
        }

    def analyze(self) -> dict:
        """
        전체 데이터, 휴식(Relax) 구간, 동작(Motion) 구간에 대한 통계를 분석합니다.
        Transition 구간은 모든 통계에서 제외됩니다.

        Returns:
            dict: 'overall', 'relax', 'motion' 키를 포함하는 중첩 딕셔너리
        """
        logger.info(f"{self.file_prefix} analysis started.")

        stats = {}

        # 1. 전체 통계 (Transition 제외)
        stats['overall'] = self.calculate_statistics(self.data)

        # 2. 휴식 구간 통계
        if 'Label' in self.data.columns:
            relax_data = self.data[self.data['Label'] == 'Relax']
            stats['relax'] = self.calculate_statistics(relax_data)
        else:
            stats['relax'] = self.calculate_statistics(pd.DataFrame())

        # 3. 동작 구간 통계
        if 'Label' in self.data.columns:
            motion_data = self.data[self.data['Label'] == self.motion]
            stats['motion'] = self.calculate_statistics(motion_data)
        else:
            stats['motion'] = self.calculate_statistics(pd.DataFrame())

        logger.info(f"{self.file_prefix} analysis completed.")
        return stats

    def save_summary(self, stats: dict):
        """
        분석된 통계 결과를 텍스트 파일(summary.txt)로 저장합니다.
        """
        summary_path = self.save_dir / f"{self.file_prefix}_summary.txt"

        try:
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write("=" * 50 + "\n")
                f.write(f" sEMG Analysis Summary Report\n")
                f.write("=" * 50 + "\n")
                f.write(f"Date    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Muscle  : {self.muscle}\n")
                f.write(f"Motion  : {self.motion}\n")
                f.write(f"Trial   : {self.trial:03d}\n")
                f.write(f"Protocol: Relax(5s) → Transition(1s) → {self.motion}(5s) → Transition(1s) → Relax(5s)\n")
                f.write(f"Note    : Transition segments excluded from statistics\n\n")

                sections = [('Overall', 'overall'),
                            ('Relax', 'relax'),
                            (f'{self.motion} (Motion)', 'motion')]

                for section_name, key in sections:
                    f.write(f"[{section_name} Statistics]\n")
                    f.write("-" * 30 + "\n")
                    s = stats.get(key, {})
                    f.write(f"Mean : {s.get('Mean', 0):.6f}\n")
                    f.write(f"Max  : {s.get('Max', 0):.6f}\n")
                    f.write(f"Min  : {s.get('Min', 0):.6f}\n")
                    f.write(f"Std  : {s.get('Std', 0):.6f}\n")
                    f.write(f"RMS  : {s.get('RMS', 0):.6f}  (200ms sliding window mean)\n")
                    f.write(f"MAV  : {s.get('MAV', 0):.6f}\n")
                    f.write(f"IEMG : {s.get('IEMG', 0):.6f}\n\n")

            logger.info(f"Summary file saved: {summary_path}")
        except Exception as e:
            logger.error(f"Error saving summary file: {e}")

    def save_graphs(self):
        """
        matplotlib을 사용하여 분석 그래프를 생성하고 저장합니다.
        Transition 구간은 회색으로 표시됩니다.
        """
        if self.data.empty or 'Time' not in self.data.columns or 'Envelope' not in self.data.columns:
            logger.warning("Cannot generate graphs: data is empty or missing required columns.")
            return

        time_arr = self.data['Time'].values
        envelope = self.data['Envelope'].values.astype(np.float64)
        labels = self.data['Label'].values if 'Label' in self.data.columns else np.array([''] * len(self.data))

        # Smoothed Envelope 계산
        if _has_signal_processing:
            smoothed = EMGSignalProcessor.smooth_envelope(envelope, method='moving_average', window_ms=50)
        else:
            smoothed = _smooth_envelope(envelope, window_ms=50)

        # 색상 맵 정의
        phase_colors = {
            'Relax': ('#ecf0f1', 0.5),
            self.motion: ('#e74c3c', 0.15),
            'Transition': ('#95a5a6', 0.3),
        }

        # ─── 1. 전체 기록 (Raw Envelope + Smoothed) ───
        fig, ax = plt.subplots(figsize=(12, 5), dpi=150)
        ax.plot(time_arr, envelope, color='#bdc3c7', linewidth=0.5, alpha=0.6, label='Raw Envelope')
        ax.plot(time_arr, smoothed, color='#2c3e50', linewidth=1.5, label='Smoothed (50ms MA)')

        # 배경색 칠하기
        self._draw_phase_backgrounds(ax, time_arr, labels, phase_colors)

        ax.set_title(f"{self.muscle} - {self.motion} (Trial {self.trial:03d})", fontsize=14, pad=15)
        ax.set_xlabel('Time (s)', fontsize=12)
        ax.set_ylabel('Amplitude', fontsize=12)
        ax.legend(loc='upper right', fontsize=9)
        ax.grid(True, linestyle='--', alpha=0.7)
        fig.tight_layout()
        fig.savefig(self.save_dir / f"{self.file_prefix}.png")
        plt.close(fig)

        # ─── 2. Relax 세그먼트만 (Transition 제외) ───
        relax_mask = labels == 'Relax'
        if np.any(relax_mask):
            fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
            ax.plot(time_arr[relax_mask], smoothed[relax_mask], color='#3498db', linewidth=1.5)
            ax.set_title(f"{self.muscle} - {self.motion} (Trial {self.trial:03d}) [Relax]", fontsize=14)
            ax.set_xlabel('Time (s)', fontsize=12)
            ax.set_ylabel('Amplitude', fontsize=12)
            ax.grid(True, linestyle='--', alpha=0.7)
            fig.tight_layout()
            fig.savefig(self.save_dir / f"{self.file_prefix}_Relax.png")
            plt.close(fig)

        # ─── 3. Motion 세그먼트만 (Transition 제외) ───
        motion_mask = labels == self.motion
        if np.any(motion_mask):
            fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
            ax.plot(time_arr[motion_mask], smoothed[motion_mask], color='#e74c3c', linewidth=1.5)
            ax.set_title(f"{self.muscle} - {self.motion} (Trial {self.trial:03d}) [Motion]", fontsize=14)
            ax.set_xlabel('Time (s)', fontsize=12)
            ax.set_ylabel('Amplitude', fontsize=12)
            ax.grid(True, linestyle='--', alpha=0.7)
            fig.tight_layout()
            fig.savefig(self.save_dir / f"{self.file_prefix}_Motion.png")
            plt.close(fig)

        # ─── 4. 비교 차트 (RMS / MAV / Max 막대 그래프) ───
        stats = self.analyze()
        if 'relax' in stats and 'motion' in stats:
            fig, ax = plt.subplots(figsize=(8, 6), dpi=150)

            categories = ['RMS', 'MAV', 'Max']
            relax_vals = [stats['relax']['RMS'], stats['relax']['MAV'], stats['relax']['Max']]
            motion_vals = [stats['motion']['RMS'], stats['motion']['MAV'], stats['motion']['Max']]

            x = np.arange(len(categories))
            width = 0.35

            ax.bar(x - width / 2, relax_vals, width, label='Relax', color='#3498db', alpha=0.8)
            ax.bar(x + width / 2, motion_vals, width, label=self.motion, color='#e74c3c', alpha=0.8)

            ax.set_ylabel('Statistical Value', fontsize=12)
            ax.set_title(f"{self.muscle} - {self.motion} (Trial {self.trial:03d}) [Comparison]", fontsize=14)
            ax.set_xticks(x)
            ax.set_xticklabels(categories, fontsize=11)
            ax.legend()
            ax.grid(axis='y', linestyle='--', alpha=0.7)

            # 통계값 텍스트 추가
            max_val = max(motion_vals + relax_vals) if (motion_vals + relax_vals) else 1
            for i, v in enumerate(relax_vals):
                ax.text(i - width / 2, v + max_val * 0.01, f'{v:.1f}', ha='center', va='bottom', fontsize=8)
            for i, v in enumerate(motion_vals):
                ax.text(i + width / 2, v + max_val * 0.01, f'{v:.1f}', ha='center', va='bottom', fontsize=8)

            fig.tight_layout()
            fig.savefig(self.save_dir / f"{self.file_prefix}_Compare.png")
            plt.close(fig)

        # ─── 5. Smoothed Envelope 전용 그래프 ───
        fig, ax = plt.subplots(figsize=(12, 5), dpi=150)
        ax.plot(time_arr, smoothed, color='#2c3e50', linewidth=1.5)
        self._draw_phase_backgrounds(ax, time_arr, labels, phase_colors)
        ax.set_title(f"{self.muscle} - {self.motion} (Trial {self.trial:03d}) [Smoothed Envelope]", fontsize=14)
        ax.set_xlabel('Time (s)', fontsize=12)
        ax.set_ylabel('Amplitude (Smoothed)', fontsize=12)
        ax.grid(True, linestyle='--', alpha=0.7)
        fig.tight_layout()
        fig.savefig(self.save_dir / f"{self.file_prefix}_Smoothed.png")
        plt.close(fig)

        logger.info(f"{self.file_prefix} graphs saved successfully.")

    def _draw_phase_backgrounds(self, ax, time_arr, labels, phase_colors):
        """그래프에 phase별 배경색을 칠합니다."""
        if len(labels) == 0:
            return

        # 라벨 변경점 찾기
        label_changes = np.where(labels[:-1] != labels[1:])[0]
        boundaries = [0] + (label_changes + 1).tolist() + [len(labels)]

        for i in range(len(boundaries) - 1):
            start_idx = boundaries[i]
            end_idx = boundaries[i + 1] - 1
            current_label = labels[start_idx]

            if current_label in phase_colors:
                color, alpha = phase_colors[current_label]
                ax.axvspan(time_arr[start_idx], time_arr[min(end_idx, len(time_arr) - 1)],
                           color=color, alpha=alpha)

    def run_all(self):
        """분석, 요약 저장, 그래프 생성을 모두 실행하는 편의 메서드입니다."""
        stats = self.analyze()
        self.save_summary(stats)
        self.save_graphs()
        logger.info("All analysis tasks (statistics, summary, graphs) completed.")
