"""
LINUX BLUETOOTH PERMISSIONS NOTE (dialout group):
To connect to the Unicorn via Bluetooth on Linux Mint/Ubuntu without running as root (sudo),
your user must be part of the 'dialout' group to access /dev/rfcomm* Bluetooth serial devices.

Run this command in your terminal to fix permission denied errors:
    sudo usermod -a -G dialout $USER
(You will need to log out and log back in, or restart your computer, for this to take effect).
"""

import os
import sys
import time
import ctypes
import logging
import numpy as np
from scipy.signal import iirnotch, butter, lfilter, lfilter_zi

from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds
from pylsl import StreamInfo, StreamOutlet

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting Unicorn Hybrid Black LSL Bridge (Linux Mint / BrainFlow Edition)")

    # 1. Configuration: Ask the user for the library path and serial number
    lib_path = input("Please enter the path to 'libunicorn.so' (Press Enter to try auto-discovery or system path): ").strip()
    if lib_path:
        if os.path.exists(lib_path):
            try:
                # Pre-load the shared library so BrainFlow can find it in the process space
                ctypes.cdll.LoadLibrary(lib_path)
                logger.info(f"Successfully loaded library from {lib_path}")
            except Exception as e:
                logger.error(f"Failed to load library at {lib_path}: {e}")
        else:
            logger.warning(f"File not found at {lib_path}. BrainFlow will attempt to find it automatically.")

    serial_num = input("Please enter the Unicorn Serial Number (e.g., UN-2021.05.35) [Press Enter to auto-discover]: ").strip()

    params = BrainFlowInputParams()
    if serial_num:
        params.serial_number = serial_num

    board_id = BoardIds.UNICORN_BOARD.value
    board = BoardShim(board_id, params)

    # 2. Get board parameters
    sampling_rate = BoardShim.get_sampling_rate(board_id)
    eeg_channels = BoardShim.get_eeg_channels(board_id)
    accel_channels = BoardShim.get_accel_channels(board_id)
    gyro_channels = BoardShim.get_gyro_channels(board_id)
    battery_channel = BoardShim.get_battery_channel(board_id)
    
    # We will build a composite list of all channels we want to stream
    # Unicorn order: [8 EEG] + [3 Accel] + [3 Gyro] + [1 Battery] = 15 channels
    stream_channels = eeg_channels + accel_channels + gyro_channels + [battery_channel]
    num_stream_channels = len(stream_channels)
    
    # We only want to filter the EEG channels (typically 0-7 for Unicorn)
    logger.info(f"Device Initialization: Sampling Rate = {sampling_rate}Hz")
    logger.info(f"EEG Channels (Filtered): {eeg_channels}")
    logger.info(f"Aux Channels (Unfiltered): Accel {accel_channels}, Gyro {gyro_channels}, Batt [{battery_channel}]")

    # --- Setup Continuous Filter States ---
    # We use scipy.signal for stateful filtering across chunks to prevent edge artifacts.
    num_eeg_channels = len(eeg_channels)
    
    # 1. High-Pass Filter (1Hz) to remove DC offset / slow drift
    b_hp, a_hp = butter(4, 1.0, btype='highpass', fs=sampling_rate)
    zi_hp = lfilter_zi(b_hp, a_hp)
    z_hp = np.repeat(zi_hp[:, np.newaxis], num_eeg_channels, axis=1)

    # 2. Low-Pass Filter (50Hz) to remove high frequency noise (above typical EEG bands)
    # 50Hz also acts as an anti-aliasing filter and helps kill the 50Hz mains power base before the notch.
    b_lp, a_lp = butter(4, 50.0, btype='lowpass', fs=sampling_rate)
    zi_lp = lfilter_zi(b_lp, a_lp)
    z_lp = np.repeat(zi_lp[:, np.newaxis], num_eeg_channels, axis=1)
    
    # 3. 50Hz notch for mains power (Egypt) - very aggressive
    b50, a50 = iirnotch(50.0, 30.0, fs=sampling_rate)
    zi50 = lfilter_zi(b50, a50)
    z50 = np.repeat(zi50[:, np.newaxis], num_eeg_channels, axis=1)
    
    # 4. 100Hz notch for 1st harmonic
    b100, a100 = iirnotch(100.0, 30.0, fs=sampling_rate)
    zi100 = lfilter_zi(b100, a100)
    z100 = np.repeat(zi100[:, np.newaxis], num_eeg_channels, axis=1)

    # 3. Setup LSL Outlet
    # We will stream all relevant channels together in one chunky array
    info = StreamInfo(
        name='UnicornMint', 
        type='EEG_EXT', 
        channel_count=num_stream_channels, 
        nominal_srate=sampling_rate, 
        channel_format='float32', 
        source_id=f'unicorn_brainflow_{serial_num}'
    )
    
    # Add metadata for Unicorn montage (all 15 channels)
    chns = info.desc().append_child("channels")
    labels = ['Fz', 'C3', 'Cz', 'C4', 'Pz', 'PO7', 'Oz', 'PO8', 
              'AccX', 'AccY', 'AccZ', 'GyrX', 'GyrY', 'GyrZ', 'Battery']
              
    for label in (labels if len(labels) == num_stream_channels else [f'CH{i}' for i in range(num_stream_channels)]):
        ch = chns.append_child("channel")
        ch.append_child_value("label", label)
        if label in ['AccX', 'AccY', 'AccZ']:
            ch.append_child_value("unit", "g")
            ch.append_child_value("type", "Accelerometer")
        elif label in ['GyrX', 'GyrY', 'GyrZ']:
            ch.append_child_value("unit", "deg/s")
            ch.append_child_value("type", "Gyroscope")
        elif label == 'Battery':
            ch.append_child_value("unit", "percent")
            ch.append_child_value("type", "Battery")
        else:
            ch.append_child_value("unit", "microvolts")
            ch.append_child_value("type", "EEG")
        
    outlet = StreamOutlet(info)
    logger.info("LSL StreamOutlet 'UnicornMint' initialized successfully.")

    is_connected = False
    try:
        # Connect to the board
        board.prepare_session()
        is_connected = True
        logger.info("Successfully connected to Unicorn headset!")

        # Start streaming (ring buffer size 4096)
        board.start_stream(4096, '')
        logger.info("Data streaming started. Press Ctrl+C to stop.")

        while True:
            # Sleep slightly to allow the buffer to fill (~40ms for 10 samples at 250Hz)
            time.sleep(0.04)

            # Get whatever data is available in the internal ring buffer
            num_samples = board.get_board_data_count()
            if num_samples > 0:
                # data is returned as (num_channels, num_samples)
                data = board.get_board_data() 
                
                # 1. Extract the EEG channels to be aggressively filtered
                eeg_data = data[eeg_channels, :]
                eeg_data_T = eeg_data.T # Shape (samples, channels)
                
                # Apply 1Hz Highpass filter (Removes DC drifting)
                eeg_filtered, z_hp = lfilter(b_hp, a_hp, eeg_data_T, axis=0, zi=z_hp)
                
                # Apply 50Hz Lowpass filter (Cleans high frequencies)
                eeg_filtered, z_lp = lfilter(b_lp, a_lp, eeg_filtered, axis=0, zi=z_lp)
                
                # Apply 50Hz notch filter (kills pure AC noise)
                eeg_filtered, z50 = lfilter(b50, a50, eeg_filtered, axis=0, zi=z50)
                
                # Apply 100Hz harmonic notch filter
                eeg_filtered, z100 = lfilter(b100, a100, eeg_filtered, axis=0, zi=z100)
                
                # 2. Extract the unfiltered Auxiliary channels (Accel, Gyro, Batt)
                # Ensure they stay in shape (samples, channels)
                aux_data = data[accel_channels + gyro_channels + [battery_channel], :]
                aux_data_T = aux_data.T
                
                # 3. Reconstruct the full 15-channel output frame for this chunk
                # Column stack: [8 EEG filtered] + [7 Aux unfiltered]
                final_chunk = np.hstack((eeg_filtered, aux_data_T))
                
                # Push the combined chunk to LSL
                outlet.push_chunk(final_chunk.tolist())

    except KeyboardInterrupt:
        logger.info("Interrupted by user (Ctrl+C). Terminating...")
    except Exception as e:
        logger.error(f"Streaming error encountered: {e}")
    finally:
        # 4. Stability: Ensure session is released properly
        if is_connected:
            try:
                board.stop_stream()
                logger.info("Data streaming stopped.")
            except Exception as e:
                logger.warning(f"Error stopping stream: {e}")
                
            try:
                board.release_session()
                logger.info("Board session released. Disconnected safely.")
            except Exception as e:
                logger.warning(f"Error releasing session: {e}")

if __name__ == "__main__":
    main()
