import logging
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import matplotlib
# GUI 스레드 충돌을 방지하기 위해 백엔드를 'Agg'로 설정합니다. (PySide6와 함께 사용하기 위함)
matplotlib.use('Agg')
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)

class EMGAnalyzer:
    """
    sEMG 데이터의 통계적 분석 및 그래프 생성을 담당하는 클래스입니다.
    """
    
    def __init__(self, data: pd.DataFrame, save_dir: Path, muscle: str, motion: str, trial: int):
        """
        EMGAnalyzer 초기화
        
        Args:
            data (pd.DataFrame): 분석할 sEMG 데이터프레임 (Time, Envelope, Label 컬럼 포함)
            save_dir (Path): 결과물을 저장할 디렉토리 경로
            muscle (str): 측정된 근육 이름
            motion (str): 수행한 동작 이름
            trial (int): 시도 횟수 (예: 1, 2, 3...)
        """
        self.data = data
        self.save_dir = save_dir
        self.muscle = muscle
        self.motion = motion
        self.trial = trial
        
        # 저장할 디렉토리가 없으면 생성합니다.
        self.save_dir.mkdir(parents=True, exist_ok=True)
        
        # 파일명 생성에 사용할 공통 접두사 (Trial 번호는 3자리 0으로 채움)
        self.file_prefix = f"{self.muscle}_{self.motion}_Trial{self.trial:03d}"
        
        # matplotlib 스타일 설정 (논문 작성에 적합한 깔끔한 스타일)
        plt.style.use('seaborn-v0_8-whitegrid')
        # 한글 폰트가 깨질 수 있으므로, 맑은 고딕 등을 설정할 수도 있으나, 
        # 시스템 의존성을 줄이기 위해 기본 폰트를 사용하되, 
        # 필요한 경우 matplotlib.rc('font', family='Malgun Gothic') 등을 추가할 수 있습니다.
        # 여기서는 보편적인 설정으로 진행합니다.

    def calculate_statistics(self, data: pd.DataFrame) -> dict:
        """
        주어진 데이터프레임의 Envelope 컬럼에 대한 통계값을 계산합니다.
        
        Args:
            data (pd.DataFrame): 분석할 데이터
            
        Returns:
            dict: 계산된 통계값 딕셔너리
        """
        if data.empty or 'Envelope' not in data.columns:
            return {
                'Mean': 0.0, 'Max': 0.0, 'Min': 0.0, 'Std': 0.0,
                'RMS': 0.0, 'MAV': 0.0, 'IEMG': 0.0
            }
            
        envelope = data['Envelope'].values
        
        # 통계량 계산
        mean_val = np.mean(envelope)
        max_val = np.max(envelope)
        min_val = np.min(envelope)
        std_val = np.std(envelope)
        
        # RMS (Root Mean Square)
        rms = np.sqrt(np.mean(envelope**2))
        
        # MAV (Mean Absolute Value)
        mav = np.mean(np.abs(envelope))
        
        # IEMG (Integrated EMG): dt는 1000Hz 기준 1/1000 = 0.001초
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
        
        Returns:
            dict: 'overall', 'relax', 'motion' 키를 포함하는 중첩 딕셔너리
        """
        logger.info(f"{self.file_prefix} 분석을 시작합니다.")
        
        stats = {}
        
        # 1. 전체 통계
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
            
        logger.info(f"{self.file_prefix} 분석이 완료되었습니다.")
        return stats

    def save_summary(self, stats: dict):
        """
        분석된 통계 결과를 텍스트 파일(summary.txt)로 저장합니다.
        
        Args:
            stats (dict): analyze()에서 반환된 통계 결과 딕셔너리
        """
        summary_path = self.save_dir / f"{self.file_prefix}_summary.txt"
        
        try:
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write("=" * 50 + "\n")
                f.write(f" sEMG 분석 요약 보고서\n")
                f.write("=" * 50 + "\n")
                f.write(f"일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"근육: {self.muscle}\n")
                f.write(f"동작: {self.motion}\n")
                f.write(f"시도(Trial): {self.trial:03d}\n\n")
                
                sections = [('전체(Overall)', 'overall'), 
                            ('휴식(Relax)', 'relax'), 
                            (f'동작({self.motion})', 'motion')]
                
                for section_name, key in sections:
                    f.write(f"[{section_name} 통계]\n")
                    f.write("-" * 30 + "\n")
                    s = stats.get(key, {})
                    f.write(f"Mean : {s.get('Mean', 0):.6f}\n")
                    f.write(f"Max  : {s.get('Max', 0):.6f}\n")
                    f.write(f"Min  : {s.get('Min', 0):.6f}\n")
                    f.write(f"Std  : {s.get('Std', 0):.6f}\n")
                    f.write(f"RMS  : {s.get('RMS', 0):.6f}\n")
                    f.write(f"MAV  : {s.get('MAV', 0):.6f}\n")
                    f.write(f"IEMG : {s.get('IEMG', 0):.6f}\n\n")
                    
            logger.info(f"요약 파일이 저장되었습니다: {summary_path}")
        except Exception as e:
            logger.error(f"요약 파일 저장 중 오류 발생: {e}")

    def save_graphs(self):
        """
        matplotlib을 사용하여 분석 그래프를 생성하고 저장합니다.
        """
        if self.data.empty or 'Time' not in self.data.columns or 'Envelope' not in self.data.columns:
            logger.warning("데이터가 없거나 필수 컬럼이 부족하여 그래프를 생성할 수 없습니다.")
            return

        time = self.data['Time'].values
        envelope = self.data['Envelope'].values
        labels = self.data['Label'].values if 'Label' in self.data.columns else np.array([''] * len(self.data))
        
        # 1. 전체 기록 (Envelope vs Time) + 배경색칠
        fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
        ax.plot(time, envelope, color='#2c3e50', linewidth=1.5, label='Envelope')
        
        # 배경색 칠하기 로직 (Label 변경점 찾기)
        if 'Label' in self.data.columns:
            # 변화하는 인덱스 추출
            label_changes = np.where(labels[:-1] != labels[1:])[0]
            start_idx = 0
            for idx in label_changes:
                current_label = labels[start_idx]
                color = '#e74c3c' if current_label == self.motion else '#ecf0f1'
                alpha = 0.2 if current_label == self.motion else 0.5
                if current_label in [self.motion, 'Relax']:
                    ax.axvspan(time[start_idx], time[idx], color=color, alpha=alpha)
                start_idx = idx + 1
            # 마지막 구간
            current_label = labels[start_idx]
            color = '#e74c3c' if current_label == self.motion else '#ecf0f1'
            alpha = 0.2 if current_label == self.motion else 0.5
            if current_label in [self.motion, 'Relax']:
                ax.axvspan(time[start_idx], time[-1], color=color, alpha=alpha)

        ax.set_title(f"{self.muscle} - {self.motion} (Trial {self.trial:03d})", fontsize=14, pad=15)
        ax.set_xlabel('시간 (초)', fontsize=12)
        ax.set_ylabel('진폭', fontsize=12)
        ax.grid(True, linestyle='--', alpha=0.7)
        fig.tight_layout()
        overall_path = self.save_dir / f"{self.file_prefix}.png"
        fig.savefig(overall_path)
        plt.close(fig)
        
        # 2. Relax 세그먼트만 표시
        relax_mask = labels == 'Relax'
        if np.any(relax_mask):
            fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
            ax.plot(time[relax_mask], envelope[relax_mask], color='#3498db', linewidth=1.5)
            ax.set_title(f"{self.muscle} - {self.motion} (Trial {self.trial:03d}) [Relax]", fontsize=14)
            ax.set_xlabel('시간 (초)', fontsize=12)
            ax.set_ylabel('진폭', fontsize=12)
            ax.grid(True, linestyle='--', alpha=0.7)
            fig.tight_layout()
            relax_path = self.save_dir / f"{self.file_prefix}_Relax.png"
            fig.savefig(relax_path)
            plt.close(fig)
            
        # 3. Motion 세그먼트만 표시
        motion_mask = labels == self.motion
        if np.any(motion_mask):
            fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
            ax.plot(time[motion_mask], envelope[motion_mask], color='#e74c3c', linewidth=1.5)
            ax.set_title(f"{self.muscle} - {self.motion} (Trial {self.trial:03d}) [Motion]", fontsize=14)
            ax.set_xlabel('시간 (초)', fontsize=12)
            ax.set_ylabel('진폭', fontsize=12)
            ax.grid(True, linestyle='--', alpha=0.7)
            fig.tight_layout()
            motion_path = self.save_dir / f"{self.file_prefix}_Motion.png"
            fig.savefig(motion_path)
            plt.close(fig)

        # 4. 비교 차트 (RMS 막대 그래프 예시)
        stats = self.analyze()
        if 'relax' in stats and 'motion' in stats:
            fig, ax = plt.subplots(figsize=(8, 6), dpi=150)
            
            categories = ['RMS', 'MAV', 'Max']
            relax_vals = [stats['relax']['RMS'], stats['relax']['MAV'], stats['relax']['Max']]
            motion_vals = [stats['motion']['RMS'], stats['motion']['MAV'], stats['motion']['Max']]
            
            x = np.arange(len(categories))
            width = 0.35
            
            ax.bar(x - width/2, relax_vals, width, label='Relax', color='#3498db', alpha=0.8)
            ax.bar(x + width/2, motion_vals, width, label='Motion', color='#e74c3c', alpha=0.8)
            
            ax.set_ylabel('진폭 통계값', fontsize=12)
            ax.set_title(f"{self.muscle} - {self.motion} (Trial {self.trial:03d}) [비교]", fontsize=14)
            ax.set_xticks(x)
            ax.set_xticklabels(categories, fontsize=11)
            ax.legend()
            ax.grid(axis='y', linestyle='--', alpha=0.7)
            
            # 통계값 텍스트 추가
            for i, v in enumerate(relax_vals):
                ax.text(i - width/2, v + (max(motion_vals + relax_vals)*0.01), f'{v:.3f}', ha='center', va='bottom', fontsize=9)
            for i, v in enumerate(motion_vals):
                ax.text(i + width/2, v + (max(motion_vals + relax_vals)*0.01), f'{v:.3f}', ha='center', va='bottom', fontsize=9)
                
            fig.tight_layout()
            compare_path = self.save_dir / f"{self.file_prefix}_Compare.png"
            fig.savefig(compare_path)
            plt.close(fig)
            
        logger.info(f"{self.file_prefix} 관련 그래프가 모두 저장되었습니다.")

    def run_all(self):
        """
        분석, 요약 저장, 그래프 생성을 모두 실행하는 편의 메서드입니다.
        """
        stats = self.analyze()
        self.save_summary(stats)
        self.save_graphs()
        logger.info("모든 분석 작업(통계, 요약 저장, 그래프 생성)이 완료되었습니다.")

