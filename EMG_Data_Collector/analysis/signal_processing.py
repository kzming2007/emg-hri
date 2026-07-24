import numpy as np
import logging

logger = logging.getLogger(__name__)

try:
    from scipy.signal import butter, filtfilt
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logger.warning("scipy is not available. Some filtering functions will use moving average fallback.")


class EMGSignalProcessor:
    """EMG 신호 처리를 위한 유틸리티 클래스 (Signal processing utility for EMG data)"""
    
    @staticmethod
    def sliding_window_rms(data: np.ndarray, window_ms: int = 200, sample_rate: int = 1000) -> np.ndarray:
        """200ms 슬라이딩 윈도우 RMS 계산
        
        Args:
            data: 1D numpy array of signal values
            window_ms: window size in milliseconds (default 200ms)
            sample_rate: sampling rate in Hz (default 1000)
        
        Returns:
            np.ndarray: RMS values, same length as input (padded at edges)
        """
        window_size = int((window_ms / 1000) * sample_rate)
        if window_size <= 0:
            return np.zeros_like(data)
            
        squared_data = np.power(data, 2)
        window = np.ones(window_size) / window_size
        
        # 'same' mode pads with zeros at edges which might cause edge effects,
        # but it keeps the output length the same.
        mean_squares = np.convolve(squared_data, window, mode='same')
        
        # Avoid negative values due to floating point inaccuracies
        mean_squares = np.maximum(mean_squares, 0)
        
        return np.sqrt(mean_squares)

    @staticmethod
    def butterworth_lowpass(data: np.ndarray, cutoff: float = 6.0,
                           sample_rate: int = 1000, order: int = 4) -> np.ndarray:
        """Butterworth 저역통과 필터
        
        Args:
            data: 1D numpy array
            cutoff: cutoff frequency in Hz (default 6.0)
            sample_rate: sampling rate in Hz
            order: filter order (default 4)
        
        Returns:
            np.ndarray: filtered data
        """
        if not SCIPY_AVAILABLE:
            logger.info("Using moving average fallback for lowpass filter due to missing scipy.")
            # Simple fallback to moving average
            window_size = int((1.0 / cutoff) * sample_rate) if cutoff > 0 else 10
            window_size = max(1, window_size)
            window = np.ones(window_size) / window_size
            return np.convolve(data, window, mode='same')
            
        try:
            nyq = 0.5 * sample_rate
            normal_cutoff = cutoff / nyq
            b, a = butter(order, normal_cutoff, btype='low', analog=False)
            
            # Additional check to ensure padlen is valid
            padlen = 3 * max(len(a), len(b))
            if len(data) <= padlen:
                 logger.warning("Data length too short for padding in filtfilt. Returning original data.")
                 return data
            
            y = filtfilt(b, a, data)
            return y
        except ValueError as e:
            logger.warning(f"Data length might be too short for zero-phase filtering. Returning original data. Error: {e}")
            return data
        except Exception as e:
            logger.error(f"Error during butterworth filtering: {e}")
            return data

    @staticmethod
    def smooth_envelope(data: np.ndarray, method: str = 'moving_average',
                       window_ms: int = 50, sample_rate: int = 1000) -> np.ndarray:
        """Envelope 스무딩
        
        Args:
            data: 1D numpy array
            method: 'moving_average' or 'butterworth'
            window_ms: window size for moving average (default 50ms)
            sample_rate: sampling rate in Hz
        
        Returns:
            np.ndarray: smoothed envelope, same length as input
        """
        if method == 'butterworth' and SCIPY_AVAILABLE:
            return EMGSignalProcessor.butterworth_lowpass(data, cutoff=6.0, sample_rate=sample_rate)
            
        # Default or fallback to moving_average
        window_size = int((window_ms / 1000) * sample_rate)
        if window_size <= 0:
             return data
        window = np.ones(window_size) / window_size
        return np.convolve(data, window, mode='same')

    @staticmethod
    def extract_features(data: np.ndarray, sample_rate: int = 1000) -> dict:
        """시간 도메인 특징 추출 (머신러닝용)
        
        Extract features commonly used in EMG classification:
        - RMS (Root Mean Square)
        - MAV (Mean Absolute Value)
        - IEMG (Integrated EMG)
        - WL (Waveform Length): sum of |x[i+1] - x[i]|)
        - ZC (Zero Crossing): count of sign changes
        - SSC (Slope Sign Change): count of slope direction changes
        - Mean, Max, Min, Std
        
        Returns:
            dict with feature names as keys
        """
        features = {}
        
        if len(data) == 0:
            return features
            
        # RMS (Root Mean Square)
        features['RMS'] = float(np.sqrt(np.mean(np.square(data))))
        
        # MAV (Mean Absolute Value)
        features['MAV'] = float(np.mean(np.abs(data)))
        
        # IEMG (Integrated EMG)
        features['IEMG'] = float(np.sum(np.abs(data)))
        
        # WL (Waveform Length)
        if len(data) > 1:
            features['WL'] = float(np.sum(np.abs(np.diff(data))))
        else:
            features['WL'] = 0.0
            
        # ZC (Zero Crossing)
        if len(data) > 1:
            signs = np.sign(data)
            signs[signs == 0] = -1 # Treat 0 as negative to avoid dropping crossings at 0
            features['ZC'] = int(np.sum(np.diff(signs) != 0))
        else:
             features['ZC'] = 0
             
        # SSC (Slope Sign Change)
        if len(data) > 2:
            diffs = np.diff(data)
            # Find where slope changes sign
            features['SSC'] = int(np.sum(diffs[:-1] * diffs[1:] < 0))
        else:
            features['SSC'] = 0
            
        # Basic statistics
        features['Mean'] = float(np.mean(data))
        features['Max'] = float(np.max(data))
        features['Min'] = float(np.min(data))
        features['Std'] = float(np.std(data))
        
        return features
