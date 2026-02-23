import sys
import time
import logging
import numpy as np
from pylsl import StreamInlet, resolve_byprop
import colorama
from colorama import Fore, Back, Style

colorama.init()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Threshold for EMG Artifact (Jaw Clench) in microvolts
# Jaw clenches create massive broadband noise. Normal EEG is ~20uV
# A clench is usually > 100uV
THRESH_CLENCH_UV = 100.0

def main():
    logger.info(Fore.CYAN + "Looking for 'UnicornMint' LSL stream..." + Style.RESET_ALL)
    
    streams = resolve_byprop('name', 'UnicornMint', timeout=5.0)
    if not streams:
        logger.error(Fore.RED + "No stream found! Run main_linux.py first." + Style.RESET_ALL)
        sys.exit(1)
        
    inlet = StreamInlet(streams[0])
    logger.info(Fore.GREEN + "Connected! Starting live Jaw Clench detection..." + Style.RESET_ALL)
    logger.info("Clench your jaw to trigger the AI detector.\n")
    
    fs = 250
    # Window size: 0.25 seconds of data (creates a fast, responsive detector)
    buffer_size = int(fs * 0.25) 
    
    while True:
        # We wait until we have a chunk of 0.25s (62 samples)
        chunk, timestamps = inlet.pull_chunk(timeout=1.0)
        
        if timestamps and len(timestamps) >= buffer_size:
            data = np.array(chunk) # shape: (samples, channels)
            
            # Extract just the first 8 EEG channels to calculate variance
            # We ignore Accel/Gyro so movement doesn't falsely trigger it
            eeg_data = data[:, :8]
            
            # Simple feature extraction: Calculate the variance/deviation across the window
            # A jaw clench will make the signal swing wildly.
            # We take the peak-to-peak (max - min) amplitude for each channel
            peak_to_peak = np.ptp(eeg_data, axis=0)
            
            # Average peak-to-peak across all 8 channels
            mean_ptp = np.mean(peak_to_peak)
            
            # Classify based on the amplitude severity
            if mean_ptp > THRESH_CLENCH_UV * 2:
                print(Back.RED + Fore.WHITE + " 🛑 MASSIVE JAW CLENCH DETECTED! 🛑 " + Style.RESET_ALL + f" (Amplitude: {mean_ptp:.1f} uV)")
            elif mean_ptp > THRESH_CLENCH_UV:
                print(Back.YELLOW + Fore.BLACK + " ⚠️ MILD CLENCH / BLINK ⚠️ " + Style.RESET_ALL + f" (Amplitude: {mean_ptp:.1f} uV)")
            else:
                # Normal brainwaves
                bar_length = int(mean_ptp / 5)
                bar = "█" * min(bar_length, 40)
                print(Fore.GREEN + f"Relaxed: {bar}" + Style.RESET_ALL + f" ({mean_ptp:.1f} uV)")
            
            # Sleep slightly to not spam the console
            time.sleep(0.05)
            
if __name__ == '__main__':
    main()
