import os
import sys
import asyncio
import logging
import socketio
from pylsl import StreamInfo, StreamOutlet

# Load environment variables (e.g., GEMINI_API_KEY)
from dotenv import load_dotenv
load_dotenv()

from sensor import SensorLayer, FatigueTimer
from classifier import FocusClassifier
from reasoning import BurnoutDetector

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("TelosEngine")

async def main():
    print("\n" + "="*50)
    print("🚀 INITIALIZING TELOS NEURO-REFLEX ENGINE 🚀")
    print("="*50)
    
    serial_num = input("Enter Unicorn Serial Number (or press Enter for auto-discover): ").strip()
    
    # Initialize Core Modules
    sensor = SensorLayer(serial_num)
    classifier = FocusClassifier(sampling_rate=sensor.sampling_rate)
    fatigue = FatigueTimer()
    burnout = BurnoutDetector()
    
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

    # State management for UI Calibration
    calib_state = "IDLE" # IDLE, REST, FOCUS, DONE
    
    @sio.on('request_calibration')
    async def on_calib_request(data):
        nonlocal calib_state
        logger.info("UI requested new calibration.")
        classifier.reset_calibration_data()
        calib_state = "START_REST"

    try:
        # Start Sensor Layer
        sensor.start()
        
        logger.info("System fully operational. Subconscious Event Loop active.")
        
        # ---------------------------------------------------------
        # MAIN REFLEX LOOP (1 Hz)
        # ---------------------------------------------------------
        while True:
            # Yield to asyncio loop
            await asyncio.sleep(1.0)
            
            # Get roughly 1-second of data from the internal buffer
            eeg_chunk = sensor.get_data()
            if eeg_chunk.size == 0:
                continue

            # --- Async Calibration State Machine ---
            if calib_state == "START_REST":
                logger.info("Calibration sequence initiated. Preparing for baseline recording...")
                for i in range(3, 0, -1):
                    logger.info(f"Calibration Prep: Starting in {i}...")
                    await sio.emit('calib_status', {'state': 'PREP', 'countdown': i})
                    await asyncio.sleep(1.0)
                
                logger.info(">>> RECORDING REST BASELINE (10s) - RELAX YOUR MIND <<<")
                await sio.emit('calib_status', {'state': 'REST', 'duration': 10})
                calib_state = "COLLECT_REST"
                calib_end_time = time.time() + 10
                continue
            
            elif calib_state == "COLLECT_REST":
                remaining = int(max(0, calib_end_time - time.time()))
                if remaining % 2 == 0: # Log every 2 seconds to avoid spam but show progress
                    logger.info(f"Collecting REST data... {remaining}s remaining")
                
                classifier.collect_rest_data(eeg_chunk)
                if time.time() >= calib_end_time:
                    logger.info("REST baseline recorded successfully.")
                    calib_state = "START_FOCUS"
                continue
            
            elif calib_state == "START_FOCUS":
                logger.info("Preparing for active focus recording...")
                for i in range(3, 0, -1):
                    logger.info(f"Phase Transition: Focus starts in {i}...")
                    await sio.emit('calib_status', {'state': 'PREP_FOCUS', 'countdown': i})
                    await asyncio.sleep(1.0)

                logger.info(">>> RECORDING ACTIVE FOCUS (10s) - CONCENTRATE INTENTLY <<<")
                await sio.emit('calib_status', {'state': 'FOCUS', 'duration': 10})
                calib_state = "COLLECT_FOCUS"
                calib_end_time = time.time() + 10
                continue
                
            elif calib_state == "COLLECT_FOCUS":
                remaining = int(max(0, calib_end_time - time.time()))
                if remaining % 2 == 0:
                    logger.info(f"Collecting FOCUS data... {remaining}s remaining")
                    
                classifier.collect_focus_data(eeg_chunk)
                if time.time() >= calib_end_time:
                    logger.info("FOCUS data recorded successfully. Finalizing model...")
                    classifier.finalize_calibration()
                    calib_state = "DONE"
                    await sio.emit('calib_status', {'state': 'DONE'})
                    logger.info("✅ Calibration complete. Neural substrate aligned.")
                continue
            
            # --- Normal Inference ---
            if not classifier.is_calibrated:
                # If not calibrated, we only stream 0.5 as a neutral value
                outlet.push_sample([0.5])
                continue

            # 1. Classify Focus (Riemannian Geometry)
            focus_prob = classifier.infer(eeg_chunk)
            
            # 2. Push Real-Time Signal to Visualization Engine
            outlet.push_sample([focus_prob])
            
            # 3. Track Fatigue Context (High Load = Focus >= 0.6)
            fatigue.update(is_high_load=(focus_prob >= 0.6))
            fatigue_mins = fatigue.get_duration_minutes()
            
            # Debug tracking out to console occasionally
            if int(time.time()) % 10 == 0:
                logger.info(f"Status | Focus: {focus_prob:.2f} | Cont. Load: {fatigue_mins:.1f}m")
            
            # 4. Neural-Symbolic Reasoning (Gemini Flash Lite)
            action_payload = burnout.check_burnout(focus_prob, fatigue_mins)
            
            if action_payload:
                # Output Action to Application
                action_str = action_payload.get("action")
                logger.warning(f"⚠️ SYSTEM REFLEX TRIGGERED: {action_str} ⚠️")
                logger.warning(f"Reason: {action_payload.get('reason_triggered')}")
                
                if sio.connected:
                    try:
                        await sio.emit('neuro_action', action_payload)
                        logger.info(f"Socket.IO Emit Success: {action_payload}")
                    except Exception as e:
                        logger.error(f"Socket.IO Emit Exception: {e}")
                        
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

import time # Need for the modulo logging block

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
