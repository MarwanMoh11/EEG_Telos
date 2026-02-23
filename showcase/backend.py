import asyncio
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import socketio
from pylsl import StreamInlet, resolve_byprop
import uvicorn
import os

# Configure Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ShowcaseBackend")

# 1. Setup Socket.IO ASGI Server
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
app = FastAPI()
socket_app = socketio.ASGIApp(sio, app)

# Mount Static Files for the Frontend
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def get_index():
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(static_dir, "index.html"))

# 2. Socket.IO Events
@sio.event
async def connect(sid, environ):
    logger.info(f"Client connected: {sid}")

@sio.event
async def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")

@sio.event
async def neuro_action(sid, data):
    """Receives commands from Engine and broadcasts to BROWSER."""
    logger.info(f"Broadcast Action received from Engine: {data}")
    await sio.emit('ui_action', data)

@sio.event
async def request_calibration(sid, data):
    """Receives request from BROWSER and broadcasts to ENGINE."""
    logger.info(f"Calibration requested by UI (sid: {sid})")
    await sio.emit('request_calibration', data)

@sio.event
async def calib_status(sid, data):
    """Receives status from ENGINE and broadcasts to BROWSER."""
    logger.info(f"Calibration status from Engine: {data}")
    await sio.emit('calib_status', data)

# 3. LSL Bridge Task
async def lsl_bridge():
    """
    Resolves the 'TelosFocus' LSL stream and pushes values to WebSockets.
    """
    logger.info("LSL Bridge: Searching for 'TelosFocus' stream...")
    inlet = None
    
    while True:
        try:
            if inlet is None:
                streams = resolve_byprop('name', 'TelosFocus', timeout=2.0)
                if streams:
                    inlet = StreamInlet(streams[0])
                    logger.info("LSL Bridge: Connected to 'TelosFocus' stream.")
                else:
                    await asyncio.sleep(2.0)
                    continue
            
            # Pull sample (timeout 1s)
            sample, timestamp = inlet.pull_sample(timeout=1.0)
            if sample:
                focus_val = float(sample[0])
                # Emit to all browsers
                await sio.emit('focus_update', {'value': focus_val})
                
        except Exception as e:
            logger.error(f"LSL Bridge Error: {e}")
            inlet = None # Try to reconnect
            await asyncio.sleep(2.0)

# 4. Lifecycle Management
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(lsl_bridge())

if __name__ == "__main__":
    # Run on port 3000 as requested for the Showcase UI
    uvicorn.run(socket_app, host="0.0.0.0", port=3000)
