import asyncio
import logging
import os
import math
from contextlib import asynccontextmanager

import numpy as np
from scipy.signal import welch
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import socketio
import uvicorn
from dotenv import load_dotenv

# Load all environment variables from .env
load_dotenv()
import sys
import os

# Add neuro_reflex to path so we can import reasoning
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'neuro_reflex'))
from reasoning import MentalStateClassifier

# Optional: LSL support (gracefully degrade if not installed)
try:
    from pylsl import StreamInlet, resolve_byprop
    HAS_LSL = True
except ImportError:
    HAS_LSL = False

# Configure Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TelosCommandCenter")

# ─── Socket.IO ───────────────────────────────────────────────
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

# ─── Global AI Instances ─────────────────────────────────────
mental_state_ai = MentalStateClassifier()
latest_focus_ratio = 0.5
latest_alpha_power = 0.0
latest_beta_power = 0.0
latest_alpha_asymmetry = 0.0
latest_artifact = 'relaxed'

# ─── Global State ────────────────────────────────────────────
state = {
    'data_source': 'synthetic',  # 'synthetic' or 'device'
    'lsl_connected': False,
    'stream_name': None,
    'engine_proc': None,

    # Synthetic generator state
    'syn_clench': False,
    'syn_blink': False,
    'syn_focus': False,
    'syn_mood': 'neutral', # 'frustrated', 'neutral', 'motivated'
    'syn_noise_level': 'realistic', # 'clean', 'realistic', 'high', 'extreme'

    # Shared data buffer (latest chunk for FFT / artifact)
    'eeg_buffer': np.zeros((8, 500), dtype=np.float32),  # rolling 2s @ 250Hz
    'buffer_ptr': 0,
}

SAMPLING_RATE = 250
CHANNEL_NAMES = ['Fz', 'C3', 'Cz', 'C4', 'Pz', 'PO7', 'Oz', 'PO8']

# ─── Synthetic Generator ────────────────────────────────────
async def synthetic_loop():
    """Generates synthetic EEG data internally at ~250Hz in chunks."""
    logger.info("[Synthetic] Generator ready.")
    chunk_size = 10  # 10 samples per push (~40ms)
    sleep_time = chunk_size / SAMPLING_RATE
    start_time = asyncio.get_event_loop().time()

    while True:
        if state['data_source'] != 'synthetic':
            await asyncio.sleep(0.5)
            continue

        await asyncio.sleep(sleep_time)
        t = asyncio.get_event_loop().time() - start_time
        timestamps = np.linspace(t - sleep_time, t, chunk_size, endpoint=False)

        chunk = np.zeros((8, chunk_size), dtype=np.float32)

        # Physics for variable noise injection
        noise_level = state['syn_noise_level']
        # Baseline drift physics (slow wandering)
        drift = 0.0
        if noise_level == 'realistic': drift = 15.0 * np.sin(2 * np.pi * 0.1 * timestamps)
        elif noise_level == 'high': drift = 40.0 * np.sin(2 * np.pi * 0.2 * timestamps) + 20.0 * np.cos(2 * np.pi * 0.05 * timestamps)
        elif noise_level == 'extreme': drift = 150.0 * np.sin(2 * np.pi * 0.5 * timestamps) + np.random.normal(0, 50, chunk_size)

        # Mains Hum (50Hz UK/EU or 60Hz US)
        mains_hum = 0.0
        if noise_level == 'realistic': mains_hum = 5.0 * np.sin(2 * np.pi * 50.0 * timestamps)
        elif noise_level >= 'high': mains_hum = 25.0 * np.sin(2 * np.pi * 50.0 * timestamps)
        
        # Base ambient random noise
        ambient_noise = np.random.normal(0, 2.0, chunk_size)
        if noise_level == 'realistic': ambient_noise = np.random.normal(0, 5.0, chunk_size)
        elif noise_level == 'high': ambient_noise = np.random.normal(0, 15.0, chunk_size)
        elif noise_level == 'extreme': ambient_noise = np.random.normal(0, 60.0, chunk_size)
        
        for i in range(8):
            alpha_mult = 5.0 if state['syn_focus'] else 15.0
            beta_mult = 15.0 if state['syn_focus'] else 5.0

            # Inject Emotional Spectrum (Hemispheric Asymmetry) on C3 (Left=1) and C4 (Right=3)
            if state['syn_mood'] == 'motivated':
                if i == 1: alpha_mult *= 0.5 # Less Alpha on Left (Approach)
                if i == 3: alpha_mult *= 1.5 # More Alpha on Right
            elif state['syn_mood'] == 'frustrated':
                if i == 1: alpha_mult *= 1.5 # More Alpha on Left
                if i == 3: alpha_mult *= 0.5 # Less Alpha on Right (Withdrawal)

            alpha = alpha_mult * np.sin(2 * np.pi * 10.0 * timestamps)
            beta = beta_mult * np.sin(2 * np.pi * 20.0 * timestamps)

            emg = np.zeros(chunk_size)
            if state['syn_clench']:
                emg = 40.0 * np.sin(2 * np.pi * 60.0 * timestamps) + np.random.normal(0, 30.0, chunk_size)

            # Assemble the signal
            pure_signal = alpha * np.cos(i) + beta * np.sin(i) + emg
            total_noise = ambient_noise + mains_hum + drift
            
            # Extreme mode: loose electrode simulation (clipping & massive noise burst)
            if noise_level == 'extreme' and np.random.random() < 0.05:
                 total_noise += np.random.choice([1, -1]) * 400.0  # Rail clipping

            chunk[i, :] = pure_signal + total_noise

        # Blink artifact on frontal channels
        if state['syn_blink']:
            blink_pulse = 100.0 * np.sin(np.pi * np.linspace(0, 1, chunk_size))
            chunk[0, :] += blink_pulse        # Fz
            chunk[1, :] += blink_pulse * 0.5  # C3
            chunk[3, :] += blink_pulse * 0.5  # C4
            state['syn_blink'] = False

        # Feed into shared buffer
        _feed_buffer(chunk)

        # Emit waveform to browsers (~25Hz effective)
        await sio.emit('eeg_waveform', {
            'data': chunk.tolist(),
            'channels': 8,
            'chunk_size': chunk_size
        })


# ─── LSL Device Bridge ──────────────────────────────────────
async def device_loop():
    """Connects to real UnicornMint LSL stream and relays data."""
    if not HAS_LSL:
        logger.warning("[Device] pylsl not installed. Device mode unavailable.")
        return

    logger.info("[Device] Bridge ready.")
    inlet = None

    while True:
        if state['data_source'] != 'device':
            if inlet:
                inlet = None
                state['lsl_connected'] = False
                await sio.emit('stream_status', {'connected': False})
            await asyncio.sleep(0.5)
            continue

        # Try to connect
        if inlet is None:
            # Add a small timeout to let the engine initialize if it just started
            streams = await asyncio.to_thread(resolve_byprop, 'name', 'UnicornMint', timeout=2.0)
            if streams:
                try:
                    # Try to create an inlet
                    temp_inlet = StreamInlet(streams[0], max_buflen=5)
                    # Test if it actually has data (not a zombie stream from a crashed process)
                    sample, timestamp = temp_inlet.pull_sample(timeout=1.0)
                    if not sample or not timestamp or timestamp == 0.0:
                        raise RuntimeError("pull_sample timed out, stream is dead.")
                    
                    inlet = temp_inlet
                    state['lsl_connected'] = True
                    state['stream_name'] = streams[0].name()
                    logger.info(f"[Device] Connected to '{state['stream_name']}'")
                    await sio.emit('stream_status', {'connected': True, 'stream_name': state['stream_name'], 'data_source': state['data_source']})
                except Exception as e:
                    logger.warning(f"[Device] Found LSL stream, but it appears dead (zombie): {e}")
                    await sio.emit('stream_status', {'connected': False, 'data_source': state['data_source']})
                    await asyncio.sleep(1.0)
                    continue
            else:
                await sio.emit('stream_status', {'connected': False, 'data_source': state['data_source']})
                await asyncio.sleep(1.0)
                continue

        # Pull data
        try:
            chunk_raw, timestamps = await asyncio.to_thread(inlet.pull_chunk, timeout=0.05)
            if timestamps:
                data = np.array(chunk_raw, dtype=np.float32)
                eeg = data[:, :8].T  # Shape: (8, samples)

                _feed_buffer(eeg)

                await sio.emit('eeg_waveform', {
                    'data': eeg.tolist(),
                    'channels': 8,
                    'chunk_size': eeg.shape[1]
                })
        except Exception as e:
            logger.error(f"[Device] LSL Error: {e}")
            inlet = None
            state['lsl_connected'] = False
            await sio.emit('stream_status', {'connected': False})
            await asyncio.sleep(1.0)


# ─── FFT Computation Loop ───────────────────────────────────
async def fft_loop():
    """Computes PSD from rolling buffer and emits at ~5Hz."""
    logger.info("[FFT] Spectral analyzer ready.")
    while True:
        await asyncio.sleep(0.2)  # 5Hz

        buf = state['eeg_buffer'].copy()
        if np.all(buf == 0):
            continue

        psd_all = []
        freqs_out = None
        for i in range(8):
            freqs, psd = welch(buf[i, :], fs=SAMPLING_RATE, nperseg=min(256, buf.shape[1]))
            psd = np.clip(psd, 1e-12, None)
            if freqs_out is None:
                # Only send freqs up to 50Hz
                mask = freqs <= 50
                freqs_out = freqs[mask].tolist()
            psd_all.append(psd[freqs <= 50].tolist())

        await sio.emit('fft_update', {
            'freqs': freqs_out,
            'psd': psd_all,
        })

        # Compute Alpha/Beta ratio efficiently from already computed PSDs
        alpha_mask = (freqs >= 8) & (freqs <= 13)
        beta_mask = (freqs >= 13) & (freqs <= 30)
        
        # Convert psd_all back to a numpy array for easier spatial averaging
        psd_np = np.array(psd_all) # Shape: (8, freqs_in_range)
        # Re-get the masks for the limited 50Hz set
        mask_freqs = freqs[freqs <= 50]
        alpha_mask_small = (mask_freqs >= 8) & (mask_freqs <= 13)
        beta_mask_small = (mask_freqs >= 13) & (mask_freqs <= 30)
        
        if np.any(alpha_mask_small) and np.any(beta_mask_small):
            alpha_power = np.mean(psd_np[:, alpha_mask_small])
            beta_power = np.mean(psd_np[:, beta_mask_small])
            
            if alpha_power + beta_power > 0:
                focus_ratio = beta_power / (alpha_power + beta_power)
            else:
                focus_ratio = 0.5
            # Calculate Hemispheric Alpha Asymmetry (HAA)
            # C3 is index 1 (Left Hemisphere), C4 is index 3 (Right Hemisphere)
            alpha_C3 = np.mean(psd_np[1, alpha_mask_small])
            alpha_C4 = np.mean(psd_np[3, alpha_mask_small])
            
            # Asymmetry Formula: (Right - Left) / (Right + Left). 
            # Positive = More Left Activity (Motivation), Negative = More Right Activity (Frustration)
            # Note: Because alpha power is *inverse* to cortical activity, we invert the standard formula:
            if alpha_C4 + alpha_C3 > 0:
                alpha_asymmetry = (alpha_C4 - alpha_C3) / (alpha_C3 + alpha_C4)
            else:
                alpha_asymmetry = 0.0
                
        else:
            alpha_power = 0.0
            beta_power = 0.0
            focus_ratio = 0.5
            alpha_asymmetry = 0.0

        # Update globals for the AI classifier snapshot
        global latest_focus_ratio, latest_alpha_power, latest_beta_power, latest_alpha_asymmetry
        latest_focus_ratio = float(np.clip(focus_ratio, 0, 1))
        latest_alpha_power = float(alpha_power)
        latest_beta_power = float(beta_power)
        latest_alpha_asymmetry = float(alpha_asymmetry)

        await sio.emit('focus_update', {'value': latest_focus_ratio})


# ─── Artifact Detection Loop ────────────────────────────────
async def artifact_loop():
    """Runs peak-to-peak artifact detection on rolling buffer at ~4Hz."""
    logger.info("[Artifact] Detector ready.")
    CLENCH_THRESH = 80.0  # uV peak-to-peak on any single channel
    BLINK_THRESH = 60.0   # frontal channels only

    while True:
        await asyncio.sleep(0.25)  # 4Hz

        buf = state['eeg_buffer'].copy()
        if np.all(buf == 0):
            continue

        # Use last 0.25s of data (62 samples)
        window = buf[:, -62:]
        ptp = np.ptp(window, axis=1)  # peak-to-peak per channel
        max_ptp = float(np.max(ptp))
        mean_ptp = float(np.mean(ptp))

        # Frontal channel check for blinks
        frontal_ptp = float(ptp[0])  # Fz

        event_type = 'relaxed'
        detail = ''

        if max_ptp > CLENCH_THRESH * 2:
            event_type = 'clench_hard'
            detail = f'Massive EMG artifact ({max_ptp:.0f} µV)'
        elif max_ptp > CLENCH_THRESH:
            event_type = 'clench_mild'
            detail = f'Mild clench detected ({max_ptp:.0f} µV)'
        elif frontal_ptp > BLINK_THRESH:
            event_type = 'blink'
            detail = f'Eye blink on Fz ({frontal_ptp:.0f} µV)'

        global latest_artifact
        latest_artifact = event_type

        await sio.emit('artifact_event', {
            'type': event_type,
            'detail': detail,
            'max_ptp': max_ptp,
            'mean_ptp': mean_ptp,
            'channel_ptp': ptp.tolist(),
        })


# ─── Heartbeat Loop ─────────────────────────────────────────
async def heartbeat_loop():
    """Sends periodic status updates to all clients."""
    while True:
        await asyncio.sleep(2.0)
        await sio.emit('stream_status', {
            'connected': state['data_source'] == 'synthetic' or state['lsl_connected'],
            'data_source': state['data_source'],
            'stream_name': 'Synthetic' if state['data_source'] == 'synthetic' else (state['stream_name'] or 'Searching...'),
        })


# ─── Shared Buffer Helper ───────────────────────────────────
def _feed_buffer(chunk: np.ndarray):
    """Append chunk to rolling buffer. chunk shape: (8, N)."""
    n = chunk.shape[1]
    buf = state['eeg_buffer']
    buf_len = buf.shape[1]

    if n >= buf_len:
        state['eeg_buffer'] = chunk[:, -buf_len:]
    else:
        state['eeg_buffer'] = np.concatenate([buf[:, n:], chunk], axis=1)


# ─── Socket.IO Events ───────────────────────────────────────
@sio.event
async def connect(sid, environ):
    logger.info(f"[WS] Client connected: {sid}")
    await sio.emit('stream_status', {
        'connected': state['data_source'] == 'synthetic' or state['lsl_connected'],
        'data_source': state['data_source'],
        'stream_name': 'Synthetic' if state['data_source'] == 'synthetic' else (state['stream_name'] or 'Searching...'),
    }, to=sid)
    # Send current synthetic state
    await sio.emit('synthetic_state', {
        'clench': state['syn_clench'],
        'focus': state['syn_focus'],
    }, to=sid)


@sio.event
async def disconnect(sid):
    logger.info(f"[WS] Client disconnected: {sid}")


@sio.on('set_data_source')
async def on_set_data_source(sid, data):
    source = data.get('source', 'synthetic')
    if source in ('synthetic', 'device'):
        state['data_source'] = source
        logger.info(f"[WS] Data source changed to: {source}")
        
        proc = state.get('engine_proc')
        if source == 'device':
            if proc is None or proc.returncode is not None:
                engine_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'neuro_reflex', 'main.py')
                engine_cwd = os.path.dirname(engine_path)
                logger.info("[Device] Auto-starting neuro_reflex engine...")
                state['engine_proc'] = await asyncio.create_subprocess_exec(
                    'python3', 'main.py',
                    cwd=engine_cwd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT
                )
                
                # Auto-bypass the interactive prompt to let it auto-discover
                state['engine_proc'].stdin.write(b'\n')
                await state['engine_proc'].stdin.drain()
                
                async def pipe_logs(p):
                    while True:
                        line = await p.stdout.readline()
                        if not line:
                            break
                        msg = line.decode('utf-8', errors='replace').strip()
                        if msg:
                            # Filter out noisy C++ logs from pylsl/brainflow
                            if any(x in msg for x in ('netinterfaces.cpp', 'board_logger', 'api_config.cpp', 'common.cpp', 'data_receiver.cpp', 'Stream transmission broke')):
                                continue
                            if msg.startswith('{') or msg.startswith('"') or msg.startswith('}') or msg.startswith('ip_add'):
                                continue
                            await sio.emit('engine_log', {'msg': msg})
                            
                async def monitor_engine(p):
                    await p.wait()
                    logger.warning(f"[Device] Engine exited with code {p.returncode}")
                    if p == state.get('engine_proc'):
                        state['engine_proc'] = None
                        if state['data_source'] == 'device':
                            logger.error("[Device] Connection failed. Reverting to Synthetic.")
                            await sio.emit('connection_error', {
                                'title': 'Engine Crash',
                                'msg': f'The neuro_reflex engine exited unexpectedly (Code: {p.returncode}).'
                            })
                
                asyncio.create_task(pipe_logs(state['engine_proc']))
                asyncio.create_task(monitor_engine(state['engine_proc']))
        elif source == 'synthetic':
            if proc and proc.returncode is None:
                logger.info("[Device] Terminating neuro_reflex engine...")
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                state['engine_proc'] = None

        await sio.emit('stream_status', {
            'connected': source == 'synthetic' or state['lsl_connected'],
            'data_source': source,
            'stream_name': 'Synthetic' if source == 'synthetic' else (state['stream_name'] or 'Searching...'),
        })


@sio.on('set_synthetic_state')
async def on_set_synthetic_state(sid, data):
    for key in ['clench', 'blink', 'focus']:
        if key in data:
            state[f'syn_{key}'] = data[key]
    logger.info(f"[Synthetic] State update: clench={state['syn_clench']}, focus={state['syn_focus']}, blink={state['syn_blink']}")
    await sio.emit('synthetic_state', {
        'clench': state['syn_clench'],
        'focus': state['syn_focus'],
        'noise_level': state['syn_noise_level']
    })

@sio.on('set_noise_level')
async def set_noise_level(sid, data):
    noise = data.get('level', 'realistic')
    state['syn_noise_level'] = noise
    logger.info(f"Updated synthetic noise profile to: {noise}")
    # Broadcast to all clients to keep UI in sync
    await sio.emit('synthetic_state', {
        'clench': state['syn_clench'],
        'blink': state['syn_blink'],
        'focus': state['syn_focus'],
        'mood': state.get('syn_mood', 'neutral'),
        'noise_level': state['syn_noise_level']
    })

@sio.on('set_mood')
async def set_mood(sid, data):
    mood = data.get('mood', 'neutral')
    state['syn_mood'] = mood
    logger.info(f"Updated synthetic mood state to: {mood}")
    # Broadcast to clients
    await sio.emit('synthetic_state', {
        'clench': state['syn_clench'],
        'blink': state['syn_blink'],
        'focus': state['syn_focus'],
        'mood': state['syn_mood'],
        'noise_level': state['syn_noise_level']
    }, skip_sid=sid)

@sio.on('request_classification')
async def on_classification_request(sid, data):
    logger.info(f"🧠 Classification Requested. Focus: {latest_focus_ratio:.2f} Alpha: {latest_alpha_power:.2f} Beta: {latest_beta_power:.2f} Asym: {latest_alpha_asymmetry:.2f}")
    noise_param = data.get('noise_level', 'clean') if state['data_source'] == 'synthetic' else 'live_device'
    
    # Run classification asynchronously so we don't block the backend loops
    def run_ai():
        return mental_state_ai.classify_state(latest_focus_ratio, latest_alpha_power, latest_beta_power, latest_alpha_asymmetry, noise_param, latest_artifact)
        
    result = await asyncio.to_thread(run_ai)
    await sio.emit('classification_result', result)

@sio.on('get_stream_status')
async def on_get_stream_status(sid, data=None):
    await sio.emit('stream_status', {
        'connected': state['data_source'] == 'synthetic' or state['lsl_connected'],
        'data_source': state['data_source'],
        'stream_name': 'Synthetic' if state['data_source'] == 'synthetic' else (state['stream_name'] or 'Searching...'),
    }, to=sid)


# Proxy calibration events (for when neuro_reflex engine is running)
@sio.event
async def request_calibration(sid, data):
    logger.info(f"[Proxy] Calibration requested by {sid}")
    await sio.emit('request_calibration', data)

@sio.event
async def calib_status(sid, data):
    logger.info(f"[Proxy] calib_status: {data}")
    await sio.emit('calib_status', data)

@sio.event
async def neuro_action(sid, data):
    logger.info(f"[Proxy] neuro_action: {data}")
    await sio.emit('ui_action', data)


# ─── App Lifecycle ───────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Telos Command Center starting up...")
    tasks = [
        asyncio.create_task(synthetic_loop()),
        asyncio.create_task(device_loop()),
        asyncio.create_task(fft_loop()),
        asyncio.create_task(artifact_loop()),
        asyncio.create_task(heartbeat_loop()),
    ]
    yield
    logger.info("Shutting down...")
    
    proc = state.get('engine_proc')
    if proc and proc.returncode is None:
        logger.info("[Device] Terminating neuro_reflex engine...")
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(lifespan=lifespan)
socket_app = socketio.ASGIApp(sio, app)

# Static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def get_index():
    return FileResponse(os.path.join(static_dir, "index.html"))


if __name__ == "__main__":
    logger.info("Starting Uvicorn on http://0.0.0.0:3000")
    uvicorn.run(socket_app, host="0.0.0.0", port=3000, log_level="info")
