import time
import logging
import numpy as np
from scipy.signal import iirnotch, butter, lfilter, lfilter_zi
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds

logger = logging.getLogger(__name__)

class FatigueTimer:
    """Tracks the continuous or cumulative duration of high-cognitive load."""
    def __init__(self):
        self.high_load_duration = 0.0  # in seconds
        self.last_update_time = time.time()
    
    def update(self, is_high_load: bool):
        current_time = time.time()
        dt = current_time - self.last_update_time
        self.last_update_time = current_time
        
        if is_high_load:
            self.high_load_duration += dt
        else:
            # For this MVP, we assume fatigue dissipates a bit when not under high load
            # OR we can just track cumulative high-load time. We will just track cumulative
            # for the session, but decay it slowly when resting.
            # Let's use a slow decay to simulate recovery.
            self.high_load_duration = max(0.0, self.high_load_duration - dt * 0.5)
            
    def get_duration_minutes(self) -> float:
        return self.high_load_duration / 60.0

class SensorLayer:
    """Handles Data Acquisition from the Unicorn board and Signal Processing."""
    def __init__(self, serial_num: str = ""):
        self.board_id = BoardIds.UNICORN_BOARD.value
        params = BrainFlowInputParams()
        if serial_num:
            params.serial_number = serial_num
            
        self.board = BoardShim(self.board_id, params)
        self.sampling_rate = BoardShim.get_sampling_rate(self.board_id)
        self.eeg_channels = BoardShim.get_eeg_channels(self.board_id)
        self.num_eeg_channels = len(self.eeg_channels)
        
        # Setup continuous stateful filters
        # 1. Bandpass 1-50Hz (Using Highpass 1Hz + Lowpass 50Hz)
        self.b_hp, self.a_hp = butter(4, 1.0, btype='highpass', fs=self.sampling_rate)
        zi_hp = lfilter_zi(self.b_hp, self.a_hp)
        self.z_hp = np.repeat(zi_hp[:, np.newaxis], self.num_eeg_channels, axis=1)

        self.b_lp, self.a_lp = butter(4, 50.0, btype='lowpass', fs=self.sampling_rate)
        zi_lp = lfilter_zi(self.b_lp, self.a_lp)
        self.z_lp = np.repeat(zi_lp[:, np.newaxis], self.num_eeg_channels, axis=1)
        
        # 2. Notch Filter 50Hz (Egypt power grid)
        self.b50, self.a50 = iirnotch(50.0, 30.0, fs=self.sampling_rate)
        zi50 = lfilter_zi(self.b50, self.a50)
        self.z50 = np.repeat(zi50[:, np.newaxis], self.num_eeg_channels, axis=1)

    def start(self):
        try:
            self.board.prepare_session()
            self.board.start_stream(4096, '')
            logger.info("SensorLayer successfully connected to Unicorn and started streaming.")
        except Exception as e:
            logger.error(f"Failed to start SensorLayer: {e}")
            logger.error("NOTE: On Linux, ensure the device isn't busy. If running via Bluetooth, assure your user is in the 'dialout' group.")
            raise

    def stop(self):
        if self.board.is_prepared():
            self.board.stop_stream()
            self.board.release_session()
            logger.info("SensorLayer disconnected safely.")

    def get_data(self):
        """Returns filtered EEG data chunk."""
        num_samples = self.board.get_board_data_count()
        if num_samples == 0:
            return np.array([])
            
        data = self.board.get_board_data()
        eeg_data = data[self.eeg_channels, :]
        eeg_data_T = eeg_data.T # Shape (samples, channels)
        
        # Apply 1Hz Highpass
        eeg_filtered, self.z_hp = lfilter(self.b_hp, self.a_hp, eeg_data_T, axis=0, zi=self.z_hp)
        
        # Apply 50Hz Lowpass
        eeg_filtered, self.z_lp = lfilter(self.b_lp, self.a_lp, eeg_filtered, axis=0, zi=self.z_lp)
        
        # Apply 50Hz Notch
        eeg_filtered, self.z50 = lfilter(self.b50, self.a50, eeg_filtered, axis=0, zi=self.z50)
        
        # Return as (channels, samples)
        return eeg_filtered.T
