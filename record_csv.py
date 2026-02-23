import time
import csv
import sys
import logging
from pylsl import StreamInlet, resolve_byprop

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("Looking for 'UnicornMint' EEG stream on the local network...")
    
    # Resolve the LSL stream
    streams = resolve_byprop('name', 'UnicornMint', timeout=5.0)
    if not streams:
        logger.error("No stream found! Make sure main_linux.py is running.")
        sys.exit(1)
        
    inlet = StreamInlet(streams[0])
    info = inlet.info()
    fs = int(info.nominal_srate())
    num_channels = info.channel_count()
    
    # Extract channel labels from XML metadata
    ch = info.desc().child("channels").child("channel")
    labels = []
    for _ in range(num_channels):
        labels.append(ch.child_value("label"))
        ch = ch.next_sibling()
        
    if not labels or len(labels) != num_channels:
        labels = [f"CH_{i}" for i in range(num_channels)]
        
    header = ['Timestamp'] + labels
    filename = f"unicorn_recording_{int(time.time())}.csv"
    
    logger.info(f"Connected to stream. Recording {num_channels} channels at {fs}Hz.")
    logger.info(f"Saving data to: {filename}")
    logger.info("Press Ctrl+C to stop recording.")
    
    try:
        with open(filename, mode='w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            
            # Record loop
            start_time = time.time()
            samples_recorded = 0
            
            while True:
                # pull_chunk returns a list of samples and their LSL timestamps
                chunk, timestamps = inlet.pull_chunk(timeout=1.0)
                if timestamps:
                    for i in range(len(timestamps)):
                        # Row: [timestamp, ch1, ch2, ..., chN]
                        row = [timestamps[i]] + chunk[i]
                        writer.writerow(row)
                    
                    samples_recorded += len(timestamps)
                    
                    # Print status every second
                    elapsed = time.time() - start_time
                    if elapsed > 0:
                        real_srate = samples_recorded / elapsed
                        print(f"\rRecording... {samples_recorded} samples written. (Actual Rate: {real_srate:.1f} Hz)", end="", flush=True)

    except KeyboardInterrupt:
        logger.info("\nRecording stopped by user.")
    finally:
        logger.info(f"Total samples recorded: {samples_recorded}")
        logger.info(f"File saved successfully: {filename}")

if __name__ == '__main__':
    main()
