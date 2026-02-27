import os
import sys
import time
import asyncio
import logging
import numpy as np
import socketio
from pylsl import StreamInfo, StreamOutlet

# Load environment variables (e.g., GEMINI_API_KEY)
from dotenv import load_dotenv
load_dotenv()

from sensor import SensorLayer, FatigueTimer
from classifier import FocusClassifier
from reasoning import MentalStateClassifier

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("TelosEngine")

async def main():
    print("\n" + "="*50)
    print("🚀 INITIALIZING TELOS NEURO-REFLEX ENGINE 🚀")
    print("="*50)
    
    serial_num = input("Enter Unicorn Serial Number (or press Enter for auto-discover): ").strip()
    
    # Initialize Core Modules
    # ---------------------------------------------------------
    # OUTPUT 1: Socket.IO Client (Action Broadcaster)
    # ---------------------------------------------------------
    sio = socketio.AsyncClient(logger=False, engineio_logger=False)
    
    @sio.event
    async def connect():
        logger.info("Socket.IO Client connected to Telos Main UI (localhost:3000).")
        
    @sio.event
    async def disconnect():
        logger.warning("Socket.IO disconnected. Reattempting in background...")

    try:
        # Connect asynchronously but don't crash if UI is offline
        await sio.connect('http://localhost:3000')
    except socketio.exceptions.ConnectionError:
        logger.warning("UI App not found at localhost:3000. Actions will not be broadcasted visually.")

    sensor = SensorLayer(serial_num, sio_client=sio)
    classifier = FocusClassifier(sampling_rate=sensor.sampling_rate)
    fatigue = FatigueTimer()
    mental_state_ai = MentalStateClassifier()
    
    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # OUTPUT 2: LSL Outlet (Raw Signal Broadcaster)
    # ---------------------------------------------------------
    info = StreamInfo(
        name='TelosFocus',
        type='FOCUS_PROB',
        channel_count=1,
        nominal_srate=1.0, # We push updates at ~1Hz
        channel_format='float32',
        source_id=f'telos_focus_{serial_num}'
    )
    outlet = StreamOutlet(info)
    logger.info("LSL Bridge Armed -> Stream: 'TelosFocus'")

    # OUTPUT 3: LSL Outlet (Raw Bridge Proxy - Only if we own the board)
    raw_outlet = None
    if not sensor.is_lsl_mode:
        raw_info = StreamInfo(
            name='UnicornMint',
            type='EEG',
            channel_count=8,
            nominal_srate=250.0,
            channel_format='float32',
            source_id=f'unicorn_proxy_{serial_num}'
        )
        raw_outlet = StreamOutlet(raw_info)
        logger.info("[Engine] 🟢 LSL Proxy Armed: Stream 'UnicornMint' active.")

    # State management for UI Calibration
    calib_state = "IDLE" # IDLE, REST, FOCUS, DONE
    
    @sio.on('request_calibration')
    async def on_calib_request(data):
        nonlocal calib_state
        logger.info("[Engine] Received 'request_calibration' from Socket.IO.")
        classifier.reset_calibration_data()
        calib_state = "START_REST"
        logger.info("[Engine] Internal State transitioned to: START_REST")

    latest_focus_prob = 0.0
    latest_alpha = 0.0
    latest_beta = 0.0
    
    @sio.on('request_classification')
    async def on_classification_request(data):
        logger.info(f"🧠 Classification Requested from UI. Mode: {data.get('noise_level', 'clean')}")
        
        if not classifier.is_calibrated:
            await sio.emit('classification_result', {"state": "UNCALIBRATED", "insight": "Please complete calibration first."})
            return
            
        noise_param = data.get('noise_level', 'clean') if not sensor.is_lsl_mode else 'live_device'
        
        # Run classification asynchronously so we don't block the engine
        def run_ai():
            return mental_state_ai.classify_state(latest_focus_prob, latest_alpha, latest_beta, noise_param)
            
        result = await asyncio.to_thread(run_ai)
        await sio.emit('classification_result', result)

    # High-frequency data queue for internal tasks
    data_queue = asyncio.Queue()

    async def lsl_proxy_loop():
        """High-frequency (50Hz) loop to proxy raw EEG data without lag."""
        logger.info("[Engine] LSL Proxy Task started (50Hz).")
        try:
            while True:
                # 20ms sleep for ~50Hz updates
                await asyncio.sleep(0.02)
                
                # Get whatever is fresh from the board
                eeg_chunk = sensor.get_data()
                if eeg_chunk.size > 0:
                    # 1. Immediately proxy to LSL for smooth visualization
                    if raw_outlet:
                        raw_outlet.push_chunk(eeg_chunk.T.tolist())
                    
                    # 2. Add to queue for the 1Hz reflex loop
                    await data_queue.put(eeg_chunk)
        except asyncio.CancelledError:
            logger.debug("LSL Proxy Task cancelled.")

    async def reflex_loop():
        """Low-frequency (1Hz) loop for classification and reasoning."""
        nonlocal calib_state
        logger.info("System fully operational. Subconscious Event Loop active.")
        
        accumulator = [] # Accumulate ~1s of data
        
        try:
            while True:
                # Block until we have some data
                chunk = await data_queue.get()
                accumulator.append(chunk)
                
                # Once we have roughly 1s of data (250 samples)
                total_samples = sum(c.shape[1] for c in accumulator)
                if total_samples < sensor.sampling_rate:
                    continue
                
                # Flatten accumulator into one chunk
                eeg_chunk = np.concatenate(accumulator, axis=1)
                accumulator = [] # Reset

                # --- Async Calibration State Machine ---
                if calib_state == "START_REST":
                    logger.info("[Engine] Sequence: START_REST (Preparing...)")
                    for i in range(3, 0, -1):
                        logger.info(f"[Engine] Status Emit: PREP ({i}s countdown)")
                        await sio.emit('calib_status', {'state': 'PREP', 'countdown': i})
                        await asyncio.sleep(1.0)
                    
                    logger.info("[Engine] Sequence: COLLECT_REST (10s recording)")
                    await sio.emit('calib_status', {'state': 'REST', 'duration': 10})
                    calib_state = "COLLECT_REST"
                    calib_end_time = time.time() + 10
                    continue
                
                elif calib_state == "COLLECT_REST":
                    remaining = int(max(0, calib_end_time - time.time()))
                    if remaining % 2 == 0: 
                        logger.info(f"[Engine] Collecting REST data... {remaining}s remaining")
                    
                    classifier.collect_rest_data(eeg_chunk)
                    if time.time() >= calib_end_time:
                        logger.info("[Engine] Sequence: REST Phase Complete.")
                        calib_state = "START_FOCUS"
                    continue
                
                elif calib_state == "START_FOCUS":
                    logger.info("[Engine] Sequence: START_FOCUS (Preparing...)")
                    for i in range(3, 0, -1):
                        logger.info(f"[Engine] Status Emit: PREP_FOCUS ({i}s countdown)")
                        await sio.emit('calib_status', {'state': 'PREP_FOCUS', 'countdown': i})
                        await asyncio.sleep(1.0)

                    logger.info("[Engine] Sequence: COLLECT_FOCUS (10s recording)")
                    await sio.emit('calib_status', {'state': 'FOCUS', 'duration': 10})
                    calib_state = "COLLECT_FOCUS"
                    calib_end_time = time.time() + 10
                    continue
                    
                elif calib_state == "COLLECT_FOCUS":
                    remaining = int(max(0, calib_end_time - time.time()))
                    if remaining % 2 == 0:
                        logger.info(f"[Engine] Collecting FOCUS data... {remaining}s remaining")
                        
                    classifier.collect_focus_data(eeg_chunk)
                    if time.time() >= calib_end_time:
                        logger.info("[Engine] Sequence: FOCUS Phase Complete. Finalizing...")
                        try:
                            classifier.finalize_calibration()
                            calib_state = "DONE"
                            logger.info("[Engine] Status Emit: DONE")
                            await sio.emit('calib_status', {'state': 'DONE'})
                            logger.info("✅ Calibration complete. Neural substrate aligned.")
                        except Exception as calib_err:
                            logger.error(f"[Engine] Calibration Failed: {calib_err}")
                            await sio.emit('calib_status', {'state': 'ERROR', 'msg': str(calib_err)})
                            calib_state = "IDLE"
                    continue
                
                # --- Normal Inference ---
                if not classifier.is_calibrated:
                    outlet.push_sample([0.5])
                    continue

                focus_prob = classifier.infer(eeg_chunk)
                outlet.push_sample([focus_prob])
                
                # Update global states for the AI to snapshot when requested
                nonlocal latest_focus_prob, latest_alpha, latest_beta
                latest_focus_prob = focus_prob
                latest_alpha = np.mean(classifier.current_features.get('alpha', 0)) if hasattr(classifier, 'current_features') and 'alpha' in classifier.current_features else 0.5
                latest_beta = np.mean(classifier.current_features.get('beta', 0)) if hasattr(classifier, 'current_features') and 'beta' in classifier.current_features else 0.5
                
                fatigue.update(is_high_load=(focus_prob >= 0.6))
                fatigue_mins = fatigue.get_duration_minutes()
                
                if int(time.time()) % 10 == 0:
                    logger.info(f"Status | Focus: {focus_prob:.2f} | Cont. Load: {fatigue_mins:.1f}m")
                    
        except asyncio.CancelledError:
            logger.debug("Reflex Loop cancelled.")

    try:
        # Start Sensor Layer
        await sensor.start()
        
        # Run both loops concurrently
        await asyncio.gather(
            lsl_proxy_loop(),
            reflex_loop()
        )
                        
    except KeyboardInterrupt:
        logger.info("Manual termination requested by Operator.")
    except Exception as e:
        logger.error(f"Critical Engine Fault: {e}", exc_info=True)
    finally:
        logger.info("Initiating Shutdown Sequence...")
        sensor.stop()
        if sio.connected:
            await sio.disconnect()
        logger.info("Offline.")



if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
