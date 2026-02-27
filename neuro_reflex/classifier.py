import time
import logging
import numpy as np
import traceback
from pyriemann.estimation import Covariances
from pyriemann.classification import MDM

logger = logging.getLogger(__name__)

class FocusClassifier:
    """Riemannian Geometry classifier taking raw EEG and returning Focus Probability."""
    
    def __init__(self, sampling_rate: int = 250):
        self.sampling_rate = int(sampling_rate)
        self.cov_estimator = Covariances(estimator='lwf')
        self.mdm = MDM()
        self.is_calibrated = False

    def reset_calibration_data(self):
        """Clears buffers to prepare for a new calibration session."""
        self.rest_buffer = []
        self.focus_buffer = []
        self.is_calibrated = False

    def collect_rest_data(self, eeg_chunk: np.ndarray):
        """Accumulates EEG data for the Rest baseline."""
        if eeg_chunk.size > 0:
            self.rest_buffer.append(eeg_chunk)

    def collect_focus_data(self, eeg_chunk: np.ndarray):
        """Accumulates EEG data for the Active Focus state."""
        if eeg_chunk.size > 0:
            self.focus_buffer.append(eeg_chunk)

    def finalize_calibration(self):
        """Trains the MDM classifier with the accumulated buffers."""
        if not self.rest_buffer or not self.focus_buffer:
            raise ValueError("Insufficient data for calibration. Ensure both Rest and Focus buffers are populated.")
            
        rest_full = np.concatenate(self.rest_buffer, axis=1)
        focus_full = np.concatenate(self.focus_buffer, axis=1)
        
        logger.info(f"Finalizing Calibration. Rest Samples: {rest_full.shape[1]}, Focus Samples: {focus_full.shape[1]}")
        try:
            self._train_model(rest_full, focus_full)
        except Exception as e:
            logger.error(f"Training failed: {e}")
            logger.error(traceback.format_exc())
            raise e
        return True

    def _train_model(self, rest_data: np.ndarray, focus_data: np.ndarray):
        """Trains the MDM classifier with Rest (0) and Focus (1) data."""
        epochs_rest = self._chunk_into_epochs(rest_data)
        epochs_focus = self._chunk_into_epochs(focus_data)
        
        y_rest = np.zeros(len(epochs_rest), dtype=int)
        y_focus = np.ones(len(epochs_focus), dtype=int)
        
        X = np.concatenate([epochs_rest, epochs_focus], axis=0) # Shape: (trials, channels, samples)
        y = np.concatenate([y_rest, y_focus])
        
        # Riemannian Geometry pipeline
        X_cov = self.cov_estimator.fit_transform(X)
        self.mdm.fit(X_cov, y)
        self.is_calibrated = True

    def _chunk_into_epochs(self, data: np.ndarray) -> np.ndarray:
        """Splits continuous multichannel data into 1-second epochs."""
        fs = int(self.sampling_rate)
        num_epochs = int(data.shape[1] // fs)
        
        if num_epochs == 0:
            raise ValueError(f"Not enough data to create a 1-second epoch. Only got {data.shape[1]} samples.")
            
        # Truncate to exact multiple of sampling_rate
        total_samples = num_epochs * fs
        truncated_data = data[:, :total_samples]
        
        # Reshape to (channels, epochs, samples_per_epoch)
        reshaped = truncated_data.reshape(int(data.shape[0]), num_epochs, fs)
        # Transpose to (epochs, channels, samples_per_epoch) as pyriemann expects
        return reshaped.transpose(1, 0, 2)
        
    def infer(self, eeg_chunk: np.ndarray) -> float:
        """
        Takes an EEG chunk and computes distance to Mean Covariances to return focus probability.
        eeg_chunk shape: (channels, samples)
        """
        if not self.is_calibrated:
            return 0.0
            
        # We need at least a few samples to compute covariance.
        # Ideally 1 chunk is 1 second (250 samples). LWF covariance can fail if samples < channels.
        if eeg_chunk.shape[1] < eeg_chunk.shape[0]:
            return 0.0 # Not enough data
            
        # pyriemann expects shape (n_trials, n_channels, n_times)
        X = np.expand_dims(eeg_chunk, axis=0)
        
        try:
            X_cov = self.cov_estimator.transform(X)
            probs = self.mdm.predict_proba(X_cov)
            
            # Find which index corresponds to class 1.0 (Focus)
            focus_class_idx = np.where(self.mdm.classes_ == 1.0)[0][0]
            focus_prob = float(probs[0, focus_class_idx])
            
            # Provide some safety limits
            return max(0.0, min(1.0, focus_prob))
        except Exception as e:
            logger.debug(f"Covariance inference failed on small block: {e}")
            return 0.0
