import time
import logging
import numpy as np
from scipy.signal import iirnotch, lfilter, lfilter_zi
from pylsl import StreamInfo, StreamOutlet
import UnicornPy

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class UnicornBridge:
    def __init__(self, frame_length=10, fs=250.0):
        """
        Initializes the bridge with the specified frame length and sampling rate.
        
        Args:
            frame_length (int): Number of payload frames per GetData call.
            fs (float): Sampling frequency in Hz.
        """
        self.frame_length = frame_length
        self.fs = fs
        self.device = None
        self.outlet = None
        self.is_streaming = False
        
        # Unicorn Hybrid Black standard channels
        self.eeg_channels = 8
        self.unicorn_channels = 0 # Will be populated dynamically after connection
        
        # --- Real-time Filters Setup ---
        # 50Hz notch for mains power
        self.b50, self.a50 = iirnotch(50.0, 30.0, fs=self.fs)
        
        # 100Hz notch for 1st harmonic
        self.b100, self.a100 = iirnotch(100.0, 30.0, fs=self.fs)
        
        # Initialize filter states for the 8 EEG channels to avoid edge artifacts
        # We need independent state for each channel.
        zi50 = lfilter_zi(self.b50, self.a50)
        self.z50 = np.repeat(zi50[:, np.newaxis], self.eeg_channels, axis=1)
        
        zi100 = lfilter_zi(self.b100, self.a100)
        self.z100 = np.repeat(zi100[:, np.newaxis], self.eeg_channels, axis=1)

    def connect(self):
        """Discovers and connects to the primary Unicorn device."""
        try:
            available_devices = UnicornPy.GetAvailableDevices(True)
            if not available_devices:
                logger.error("No Unicorn devices found. Please ensure the headset is paired and turned on.")
                return False
                
            device_str = available_devices[0]
            logger.info(f"Attempting to connect to device: {device_str}")
            
            # Connect to device
            self.device = UnicornPy.Unicorn(device_str)
            self.unicorn_channels = self.device.GetNumberOfAcquiredChannels()
            
            logger.info(f"Successfully connected to {device_str}.")
            logger.info(f"Device streams {self.unicorn_channels} channels total.")
            
            # --- Initialize LSL Stream ---
            info = StreamInfo(
                name='UnicornEEG', 
                type='EEG', 
                channel_count=self.eeg_channels, 
                nominal_srate=self.fs, 
                channel_format='float32', 
                source_id=f'unicorn_{device_str.replace(":", "")}'
            )
            
            # Add metadata for typical Unicorn montage
            chns = info.desc().append_child("channels")
            labels = ['Fz', 'C3', 'Cz', 'C4', 'Pz', 'PO7', 'Oz', 'PO8']
            for label in labels:
                ch = chns.append_child("channel")
                ch.append_child_value("label", label)
                ch.append_child_value("unit", "microvolts")
                ch.append_child_value("type", "EEG")
                
            self.outlet = StreamOutlet(info)
            logger.info("LSL StreamOutlet initialized successfully.")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False

    def stream(self):
        """Main loop that fetches data, applies filters, and streams to LSL."""
        if self.device is None or self.outlet is None:
            logger.error("Cannot stream: Device or LSL outlet not initialized.")
            return

        # Prepare buffer sizes. Unicorn format implies floats taking 4 bytes each.
        receive_buffer_length = self.frame_length * self.unicorn_channels * 4
        receive_buffer = bytearray(receive_buffer_length)

        try:
            # False = disable test pulse mode, read actual EEG
            self.device.StartAcquisition(False) 
            self.is_streaming = True
            
            logger.info("Started data acquisition via Bluetooth.")
            logger.info("Streaming to LSL... Press Ctrl+C to stop gracefully.")
            
            while self.is_streaming:
                # Blocks until exactly `frame_length` payloads are pulled from Bluetooth buffer
                self.device.GetData(self.frame_length, receive_buffer, receive_buffer_length)
                
                # Convert raw bytes into numpy float32 buffer
                data = np.frombuffer(receive_buffer, dtype=np.float32, count=self.frame_length * self.unicorn_channels)
                
                # Reshape array to (frames, channels)
                # First 8 columns are always the EEG channels according to Unicorn specifications
                data = np.reshape(data, (self.frame_length, self.unicorn_channels))
                eeg_data = data[:, :self.eeg_channels]
                
                # Apply 50Hz notch filter (real-time aware using `zi` state)
                eeg_filtered, self.z50 = lfilter(self.b50, self.a50, eeg_data, axis=0, zi=self.z50)
                
                # Apply 100Hz notch filter
                eeg_filtered, self.z100 = lfilter(self.b100, self.a100, eeg_filtered, axis=0, zi=self.z100)
                
                # Push the chunk to LSL
                self.outlet.push_chunk(eeg_filtered.tolist())
                
        except KeyboardInterrupt:
            logger.info("Interrupted by user (Ctrl+C). Terminating...")
        except Exception as e:
            logger.error(f"Streaming error encountered: {e}")
        finally:
            self.disconnect()

    def disconnect(self):
        """Safely clean up resources and release Bluetooth handles."""
        self.is_streaming = False
        
        if self.device is not None:
            try:
                self.device.StopAcquisition()
                logger.info("Data acquisition stopped.")
            except Exception as e:
                logger.warning(f"Error stopping acquisition: {e}")
            
            try:
                del self.device
                self.device = None
                logger.info("Disconnected from device.")
            except Exception as e:
                logger.warning(f"Error disconnecting: {e}")
                
        if self.outlet is not None:
            self.outlet = None
            logger.info("LSL StreamOutlet closed.")

if __name__ == "__main__":
    bridge = UnicornBridge(frame_length=10, fs=250.0)
    
    # Run the connection and start streaming
    if bridge.connect():
        bridge.stream()
