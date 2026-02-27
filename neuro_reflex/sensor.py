import time
import logging
import numpy as np
from scipy.signal import iirnotch, butter, lfilter, lfilter_zi
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds
from pylsl import StreamInlet, resolve_byprop

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
            self.high_load_duration = max(0.0, self.high_load_duration - dt * 0.5)
            
    def get_duration_minutes(self) -> float:
        return self.high_load_duration / 60.0

class SensorLayer:
    """Handles Data Acquisition from the Unicorn board (Direct) or LSL Bridge (Fallback)."""
    def __init__(self, serial_num: str = "", sio_client=None):
        self.sio = sio_client
        self.board_id = BoardIds.UNICORN_BOARD.value
        self.serial_num = serial_num
        self.sampling_rate = 250.0 # Default for Unicorn
        self.eeg_channels = list(range(8)) # Default 0-7
        self.num_eeg_channels = 8
        self.inlet = None
        self.is_lsl_mode = False
        
        params = BrainFlowInputParams()
        if serial_num:
            params.serial_number = serial_num
        self.board = BoardShim(self.board_id, params)

        # Setup filters (Same for both modes to ensure data consistency)
        self.b_hp, self.a_hp = butter(4, 1.0, btype='highpass', fs=self.sampling_rate)
        zi_hp = lfilter_zi(self.b_hp, self.a_hp)
        self.z_hp = np.repeat(zi_hp[:, np.newaxis], self.num_eeg_channels, axis=1)

        self.b_lp, self.a_lp = butter(4, 50.0, btype='lowpass', fs=self.sampling_rate)
        zi_lp = lfilter_zi(self.b_lp, self.a_lp)
        self.z_lp = np.repeat(zi_lp[:, np.newaxis], self.num_eeg_channels, axis=1)
        
        self.b50, self.a50 = iirnotch(50.0, 30.0, fs=self.sampling_rate)
        zi50 = lfilter_zi(self.b50, self.a50)
        self.z50 = np.repeat(zi50[:, np.newaxis], self.num_eeg_channels, axis=1)

    async def start(self):
        """Attempts direct board connection, falls back to LSL if device is busy."""
        try:
            logger.info("Attempting direct connection to Unicorn headset...")
            self.board.prepare_session()
            self.board.start_stream(4096, '')
            logger.info("SensorLayer successfully connected to Unicorn and started streaming.")
        except Exception as e:
            logger.warning(f"Direct connection failed: {e}")
            logger.info("Switching to LSL Fallback Mode. Searching for 'UnicornMint' stream...")
            
            streams = resolve_byprop('name', 'UnicornMint', timeout=5.0)
            if streams:
                try:
                    temp_inlet = StreamInlet(streams[0])
                    # pylsl pull_sample returns empty lists/None on timeout, it does not raise an exception
                    sample, timestamp = temp_inlet.pull_sample(timeout=1.0)
                    if not sample or not timestamp or timestamp == 0.0:
                        raise RuntimeError("pull_sample timed out, stream is dead.")
                        
                    self.inlet = temp_inlet
                    self.is_lsl_mode = True
                    logger.info("✅ Fallback Successful: Connected to LSL stream 'UnicornMint'.")
                    return
                except Exception as e_lsl:
                    logger.warning(f"Found LSL stream, but it appears dead (zombie): {e_lsl}")
                    
            # If we get here, both direct and LSL failed
            err_msg = "No Unicorn headset OR active LSL stream found!"
            logger.error(f"❌ {err_msg}")
            
            # Emit error directly to the dashboard if socket is available
            if self.sio and self.sio.connected:
                import asyncio
                await self.sio.emit('engine_fatal_error', {'msg': err_msg})
                await asyncio.sleep(0.5) # Give the network time to send the packet before we crash
                
            raise RuntimeError("Could not establish data source.")

    def stop(self):
        if not self.is_lsl_mode and self.board.is_prepared():
            self.board.stop_stream()
            self.board.release_session()
        self.inlet = None
        logger.info("SensorLayer disconnected safely.")

    def get_data(self):
        """Returns filtered EEG data chunk from either Board or LSL."""
        if self.is_lsl_mode:
            # Pull whatever is available in the LSL buffer
            chunk, timestamps = self.inlet.pull_chunk(timeout=0.0)
            if not timestamps:
                return np.array([])
            # Shape: (samples, channels) -> extract first 8 EEG
            data = np.array(chunk)[:, :self.num_eeg_channels]
            # LSL data from main.py is ALREADY filtered (HP, LP, Notch).
            # Applying filters again would destroy the Alpha/Beta bands.
            return data.T
        else:
            num_samples = self.board.get_board_data_count()
            if num_samples == 0:
                return np.array([])
            data = self.board.get_board_data()
            eeg_data = data[self.eeg_channels, :]
            eeg_data_T = eeg_data.T # Shape (samples, channels)
        
            # Only filter raw board data (not pre-filtered LSL data)
            eeg_filtered, self.z_hp = lfilter(self.b_hp, self.a_hp, eeg_data_T, axis=0, zi=self.z_hp)
            eeg_filtered, self.z_lp = lfilter(self.b_lp, self.a_lp, eeg_filtered, axis=0, zi=self.z_lp)
            eeg_filtered, self.z50 = lfilter(self.b50, self.a50, eeg_filtered, axis=0, zi=self.z50)
        
            return eeg_filtered.T
