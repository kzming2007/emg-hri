import logging
import re
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

try:
    from analysis.signal_processing import EMGSignalProcessor
except ImportError:
    logging.warning("analysis.signal_processing module not found. Some ML features (WL, ZC, SSC) might not be calculated accurately if fallback is used.")
    EMGSignalProcessor = None

class MultiTrialAnalyzer:
    def __init__(self, muscle: str, base_dir: Path | str):
        """지정 근육 폴더에서 모든 Trial CSV를 자동 탐색
        
        Args:
            muscle: muscle name (e.g. 'FDS')
            base_dir: base data directory (e.g. 'Data')
        """
        self.muscle = muscle
        self.base_dir = Path(base_dir)
        self.muscle_dir = self.base_dir / self.muscle
        self.trial_data = []  # list of (trial_num, motion, DataFrame) tuples
        
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self._load_trials()
        
    def _load_trials(self):
        """근육 디렉토리 내의 Trial CSV 파일들을 찾아 파싱합니다."""
        if not self.muscle_dir.exists():
            self.logger.warning(f"Directory not found: {self.muscle_dir}")
            return
            
        # 파일명 패턴: {Muscle}_{Motion}_Trial{NNN}.csv
        pattern = re.compile(rf"{self.muscle}_(.*)_Trial(\d+)\.csv")
        
        for file_path in self.muscle_dir.rglob("*.csv"):
            match = pattern.match(file_path.name)
            if match:
                motion = match.group(1)
                trial_num = int(match.group(2))
                try:
                    df = pd.read_csv(file_path)
                    self.trial_data.append((trial_num, motion, df))
                    self.logger.info(f"Loaded trial {trial_num} for motion {motion} from {file_path.name}")
                except Exception as e:
                    self.logger.error(f"Failed to load {file_path}: {e}")
                    
        # Trial 번호 순으로 정렬
        self.trial_data.sort(key=lambda x: x[0])

    def get_trial_count(self) -> int:
        """찾은 총 Trial 개수 반환"""
        return len(self.trial_data)

    def get_available_motions(self) -> list[str]:
        """존재하는 유니크한 모션 이름 리스트 반환"""
        return list(set(motion for _, motion, _ in self.trial_data))

    def merge_dataset(self) -> Path | None:
        """모든 Trial CSV를 병합하여 저장합니다. (Transition 제외)"""
        if not self.trial_data:
            self.logger.warning("No trial data available to merge.")
            return None
            
        merged_df = pd.DataFrame()
        for _, _, df in self.trial_data:
            # Transition 행 제외
            valid_df = df[df['Label'] != 'Transition']
            merged_df = pd.concat([merged_df, valid_df], ignore_index=True)
            
        output_path = self.muscle_dir / f"{self.muscle}_dataset.csv"
        try:
            merged_df.to_csv(output_path, index=False)
            self.logger.info(f"Merged dataset saved to {output_path}")
            return output_path
        except Exception as e:
            self.logger.error(f"Failed to save merged dataset: {e}")
            return None

    def calculate_cross_trial_stats(self) -> dict:
        """각 모션별로 Trial 간의 통계치를 계산합니다."""
        if not self.trial_data:
            self.logger.warning("No trial data available for stats calculation.")
            return {}
            
        stats_by_motion = {}
        
        # 모션별로 Trial 데이터 그룹화
        motion_groups = {}
        for trial_num, motion, df in self.trial_data:
            if motion not in motion_groups:
                motion_groups[motion] = []
                
            # Transition 제외
            valid_df = df[df['Label'] != 'Transition']
            if valid_df.empty:
                continue
                
            envelope = valid_df['Envelope']
            
            # 특성 계산
            rms = np.sqrt(np.mean(envelope**2)) if not envelope.empty else 0
            mav = np.mean(np.abs(envelope)) if not envelope.empty else 0
            iemg = np.sum(np.abs(envelope)) if not envelope.empty else 0
            mean_val = np.mean(envelope) if not envelope.empty else 0
            max_val = np.max(envelope) if not envelope.empty else 0
            min_val = np.min(envelope) if not envelope.empty else 0
            std_val = np.std(envelope) if not envelope.empty else 0
            
            trial_stats = {
                'trial': trial_num,
                'RMS': float(rms),
                'MAV': float(mav),
                'IEMG': float(iemg),
                'Mean': float(mean_val),
                'Max': float(max_val),
                'Min': float(min_val),
                'Std': float(std_val)
            }
            motion_groups[motion].append(trial_stats)
            
        # 결과 딕셔너리 구성
        for motion, trials in motion_groups.items():
            if not trials:
                continue
                
            # 각 지표별 리스트 추출
            metrics = ['RMS', 'MAV', 'IEMG', 'Mean', 'Max', 'Min', 'Std']
            means = {}
            stds = {}
            for metric in metrics:
                values = [t[metric] for t in trials]
                means[metric] = float(np.mean(values)) if values else 0.0
                stds[metric] = float(np.std(values)) if values else 0.0
                
            stats_by_motion[motion] = {
                'trials': trials,
                'mean': means,
                'std': stds
            }
            
        return stats_by_motion

    def save_comparison_graph(self, stats: dict = None) -> Path | None:
        """모션간 비교 바 차트를 생성하여 저장합니다."""
        if not stats:
            stats = self.calculate_cross_trial_stats()
            if not stats:
                return None
                
        plt.style.use('seaborn-v0_8-whitegrid')
        fig, axes = plt.subplots(1, 3, figsize=(10, 6))
        
        motions = list(stats.keys())
        metrics = ['RMS', 'MAV', 'IEMG']
        
        for idx, metric in enumerate(metrics):
            ax = axes[idx]
            means = [stats[m]['mean'][metric] for m in motions]
            stds = [stats[m]['std'][metric] for m in motions]
            
            x_pos = np.arange(len(motions))
            ax.bar(x_pos, means, yerr=stds, capsize=5, alpha=0.7, color='skyblue', edgecolor='black')
            ax.set_xticks(x_pos)
            ax.set_xticklabels(motions)
            ax.set_title(f"{metric} Comparison")
            ax.set_ylabel(metric)
            
        plt.tight_layout()
        output_path = self.muscle_dir / f"{self.muscle}_comparison.png"
        try:
            plt.savefig(output_path, dpi=150)
            self.logger.info(f"Comparison graph saved to {output_path}")
            plt.close()
            return output_path
        except Exception as e:
            self.logger.error(f"Failed to save comparison graph: {e}")
            plt.close()
            return None

    def save_trend_graph(self, stats: dict = None) -> Path | None:
        """Trial에 따른 지표 변화 트렌드 라인 차트를 생성하여 저장합니다."""
        if not stats:
            stats = self.calculate_cross_trial_stats()
            if not stats:
                return None
                
        plt.style.use('seaborn-v0_8-whitegrid')
        fig, axes = plt.subplots(3, 1, figsize=(10, 12))
        
        motions = list(stats.keys())
        metrics = ['RMS', 'MAV', 'IEMG']
        
        for idx, metric in enumerate(metrics):
            ax = axes[idx]
            for motion in motions:
                trials = stats[motion]['trials']
                if not trials:
                    continue
                trial_nums = [t['trial'] for t in trials]
                values = [t[metric] for t in trials]
                ax.plot(trial_nums, values, marker='o', label=motion)
                
            ax.set_title(f"{metric} Trend over Trials")
            ax.set_xlabel("Trial Number")
            ax.set_ylabel(metric)
            ax.legend()
            
        plt.tight_layout()
        output_path = self.muscle_dir / f"{self.muscle}_trends.png"
        try:
            plt.savefig(output_path)
            self.logger.info(f"Trend graph saved to {output_path}")
            plt.close()
            return output_path
        except Exception as e:
            self.logger.error(f"Failed to save trend graph: {e}")
            plt.close()
            return None

    def generate_ml_dataset(self) -> Path | None:
        """머신러닝용 데이터셋 피처를 추출하여 저장합니다."""
        if not self.trial_data:
            self.logger.warning("No trial data available for ML dataset generation.")
            return None
            
        ml_records = []
        
        for trial_num, motion, df in self.trial_data:
            # Transition은 제외
            df_valid = df[df['Label'] != 'Transition']
            
            # Label 값으로 그룹화하여 세그먼트 추출
            for label, group in df_valid.groupby('Label'):
                envelope = group['Envelope'].values
                
                # 기본 피처 계산
                rms = np.sqrt(np.mean(envelope**2)) if len(envelope) > 0 else 0
                mav = np.mean(np.abs(envelope)) if len(envelope) > 0 else 0
                iemg = np.sum(np.abs(envelope)) if len(envelope) > 0 else 0
                mean_val = np.mean(envelope) if len(envelope) > 0 else 0
                max_val = np.max(envelope) if len(envelope) > 0 else 0
                min_val = np.min(envelope) if len(envelope) > 0 else 0
                std_val = np.std(envelope) if len(envelope) > 0 else 0
                
                # 고급 피처 계산 
                wl, zc, ssc = 0, 0, 0
                if EMGSignalProcessor and 'Raw' in group.columns:
                    # EMGSignalProcessor를 사용하여 피처 추출 (만약 해당 메서드가 있다면)
                    # 여기서는 지시사항에 따라 계산을 모방하거나 직접 구현
                    raw_signal = group['Raw'].values
                    diffs = np.diff(raw_signal)
                    wl = np.sum(np.abs(diffs))
                    zero_crossings = np.where(np.diff(np.sign(raw_signal)))[0]
                    zc = len(zero_crossings)
                    slope_sign_changes = np.where(np.diff(np.sign(diffs)))[0]
                    ssc = len(slope_sign_changes)
                elif 'Raw' in group.columns:
                    # Fallback calculations if EMGSignalProcessor is not imported properly
                    raw_signal = group['Raw'].values
                    diffs = np.diff(raw_signal)
                    wl = np.sum(np.abs(diffs))
                    zero_crossings = np.where(np.diff(np.sign(raw_signal)))[0]
                    zc = len(zero_crossings)
                    slope_sign_changes = np.where(np.diff(np.sign(diffs)))[0]
                    ssc = len(slope_sign_changes)
                
                record = {
                    'Muscle': self.muscle,
                    'Motion': motion,
                    'Trial': trial_num,
                    'Label': label,
                    'RMS': float(rms),
                    'MAV': float(mav),
                    'IEMG': float(iemg),
                    'Mean': float(mean_val),
                    'Max': float(max_val),
                    'Min': float(min_val),
                    'Std': float(std_val),
                    'WL': float(wl),
                    'ZC': float(zc),
                    'SSC': float(ssc)
                }
                ml_records.append(record)
                
        ml_df = pd.DataFrame(ml_records)
        output_path = self.muscle_dir / f"{self.muscle}_ml_features.csv"
        
        try:
            ml_df.to_csv(output_path, index=False)
            self.logger.info(f"ML features dataset saved to {output_path}")
            return output_path
        except Exception as e:
            self.logger.error(f"Failed to save ML features dataset: {e}")
            return None

    def save_summary_report(self, stats: dict = None, paths: dict = None) -> Path | None:
        """통계 및 처리 결과 요약 리포트를 생성합니다."""
        if not stats:
            stats = self.calculate_cross_trial_stats()
            
        output_path = self.muscle_dir / f"{self.muscle}_report.txt"
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"=== Multi-Trial Analysis Report for {self.muscle} ===\n")
                f.write(f"Total Trials Found: {self.get_trial_count()}\n")
                f.write(f"Detected Motions: {', '.join(self.get_available_motions())}\n\n")
                
                f.write("--- Cross-Trial Statistics ---\n")
                for motion, data in stats.items():
                    f.write(f"Motion: {motion}\n")
                    for metric, mean_val in data['mean'].items():
                        std_val = data['std'][metric]
                        f.write(f"  - {metric}: {mean_val:.2f} ± {std_val:.2f}\n")
                    f.write("\n")
                    
                f.write("--- Generated Files ---\n")
                if paths:
                    for key, path in paths.items():
                        if path:
                            f.write(f"  - {key}: {Path(path).name}\n")
                            
            self.logger.info(f"Summary report saved to {output_path}")
            return output_path
        except Exception as e:
            self.logger.error(f"Failed to save summary report: {e}")
            return None

    def run_all(self) -> dict:
        """모든 분석 단계를 실행하고 결과 파일 경로를 반환합니다."""
        if not self.trial_data:
            self.logger.warning("No data found. Aborting analysis.")
            return {}
            
        stats = self.calculate_cross_trial_stats()
        
        paths = {
            'merged_dataset': self.merge_dataset(),
            'comparison_graph': self.save_comparison_graph(stats),
            'trend_graph': self.save_trend_graph(stats),
            'ml_dataset': self.generate_ml_dataset()
        }
        
        paths['report'] = self.save_summary_report(stats, paths)
        
        return paths
