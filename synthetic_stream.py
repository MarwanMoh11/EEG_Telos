import sys
import tty
import termios
import threading
import time
import logging
import numpy as np
from pylsl import StreamInfo, StreamOutlet

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global State Variables for Interactivity
state = {
    'is_clenching': False,
    'blink_trigger': False,
    'is_focused': False,
    'running': True
}

def key_listener():
    """Non-blocking keyboard listener for Linux terminal."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        while state['running']:
            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                ch = sys.stdin.read(1)
                if ch == 'c':
                    state['is_clenching'] = not state['is_clenching']
                    print(f"\r[STATE] Jaw Clenching: {'ON' if state['is_clenching'] else 'OFF'}  ", end='\r\n')
                elif ch == 'b':
                    state['blink_trigger'] = True
                    print("\r[STATE] ** BLINK TRIGGERED **      ", end='\r\n')
                elif ch == 'f':
                    state['is_focused'] = not state['is_focused']
                    print(f"\r[STATE] Focus Mode: {'ON' if state['is_focused'] else 'OFF'}    ", end='\r\n')
                elif ch == 'q' or ch == '\x03': # q or Ctrl+C
                    state['running'] = False
                    print("\r[STATE] Exiting...                 ", end='\r\n')
                    break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def main():
    logger.info("Starting Interactive Synthetic Unicorn LSL Streamer")
    
    # We need select for the non-blocking input
    global select
    import select
    
    sampling_rate = 250
    num_stream_channels = 15
    
    # Setup LSL Outlet
    info = StreamInfo(
        name='UnicornMint', 
        type='EEG_EXT', 
        channel_count=num_stream_channels, 
        nominal_srate=sampling_rate, 
        channel_format='float32', 
        source_id='unicorn_brainflow_synthetic'
    )
    
    # Add metadata for Unicorn montage
    chns = info.desc().append_child("channels")
    labels = ['Fz', 'C3', 'Cz', 'C4', 'Pz', 'PO7', 'Oz', 'PO8', 
              'AccX', 'AccY', 'AccZ', 'GyrX', 'GyrY', 'GyrZ', 'Battery']
              
    for label in labels:
        ch = chns.append_child("channel")
        ch.append_child_value("label", label)
        if label in ['AccX', 'AccY', 'AccZ']:
            ch.append_child_value("type", "Accelerometer")
        elif label in ['GyrX', 'GyrY', 'GyrZ']:
            ch.append_child_value("type", "Gyroscope")
        elif label == 'Battery':
            ch.append_child_value("type", "Battery")
        else:
            ch.append_child_value("type", "EEG")
        
    outlet = StreamOutlet(info)
    logger.info("LSL StreamOutlet 'UnicornMint' initialized.")
    
    print("\n---------------------------------------------------------")
    print(" INTERACTIVE STREAM CONTROLS:")
    print(" [c] - Toggle Jaw Clench Noise (EMG interference)")
    print(" [b] - Trigger a single Eye Blink (Large frontal spike)")
    print(" [f] - Toggle Focus State (High Beta, Low Alpha)")
    print(" [q] - Quit (or Ctrl+C)")
    print("---------------------------------------------------------\n")
    
    # Start the keyboard listener thread
    listener_thread = threading.Thread(target=key_listener, daemon=True)
    listener_thread.start()
    
    start_time = time.time()
    chunk_size = 10 
    sleep_time = chunk_size / sampling_rate
    
    try:
        while state['running']:
            time.sleep(sleep_time)
            
            t = time.time() - start_time
            timestamps = np.linspace(t - sleep_time, t, chunk_size, endpoint=False)
            
            chunk = np.zeros((chunk_size, num_stream_channels), dtype=np.float32)
            
            # --- Generate Interactive Synthetic Data ---
            for i in range(8):
                # Base states
                alpha_mult = 5.0 if state['is_focused'] else 15.0  # Alpha drops when focused
                beta_mult = 15.0 if state['is_focused'] else 5.0   # Beta rises when focused
                
                # Frequencies
                alpha = alpha_mult * np.sin(2 * np.pi * 10.0 * timestamps)
                beta = beta_mult * np.sin(2 * np.pi * 20.0 * timestamps)
                
                # Base noise
                noise_mult = 20.0 if state['is_clenching'] else 5.0
                noise = np.random.normal(0, noise_mult, chunk_size)
                
                # High frequency EMG artifact from clenching
                emg_artifact = 0
                if state['is_clenching']:
                    emg_artifact = 40.0 * np.sin(2 * np.pi * 60.0 * timestamps) + np.random.normal(0, 30.0, chunk_size)
                
                # Combine base signals
                chunk[:, i] = alpha * np.cos(i) + beta * np.sin(i) + noise + emg_artifact
            
            # Handle Blink Trigger (Frontal channels Fz(0), heavily affected)
            if state['blink_trigger']:
                blink_pulse = 100.0 * np.sin(np.pi * np.linspace(0, 1, chunk_size)) # Single large half-sine wave jump
                chunk[:, 0] += blink_pulse # Fz
                chunk[:, 1] += blink_pulse * 0.5 # C3
                chunk[:, 3] += blink_pulse * 0.5 # C4
                # Reset trigger after chunk is built
                state['blink_trigger'] = False

            # Accel (channels 8, 9, 10)
            chunk[:, 8] = np.random.normal(0, 0.05, chunk_size)    # AccX 
            chunk[:, 9] = np.random.normal(0, 0.05, chunk_size)    # AccY 
            chunk[:, 10] = np.random.normal(1.0, 0.05, chunk_size) # AccZ 
            
            # Gyro (channels 11, 12, 13)
            chunk[: , 11] = np.random.normal(0, 1.0, chunk_size) # GyrX
            chunk[: , 12] = np.random.normal(0, 1.0, chunk_size) # GyrY
            chunk[: , 13] = np.random.normal(0, 1.0, chunk_size) # GyrZ
            
            # Battery (channel 14)
            chunk[:, 14] = 100.0 
            
            outlet.push_chunk(chunk.tolist())
            
    except KeyboardInterrupt:
        state['running'] = False
        print("\n\rTerminating...")
    
    # Clean exit
    logger.info("Stream stopped.")
    sys.exit(0)

if __name__ == "__main__":
    main()
