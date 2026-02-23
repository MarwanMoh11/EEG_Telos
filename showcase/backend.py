import asyncio
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import socketio
from pylsl import StreamInlet, resolve_byprop
import uvicorn
import os
from contextlib import asynccontextmanager

# Configure Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ShowcaseBackend")

# 1. Setup Socket.IO ASGI Server
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

# Global state for stream connectivity
lsl_connected = False

# 3. LSL Bridge Task
async def lsl_bridge():
    """
    Resolves the 'TelosFocus' LSL stream and pushes values to WebSockets.
    Uses asyncio.to_thread to prevent blocking the main event loop.
    """
    global lsl_connected
    logger.info("🚀 LSL Bridge Thread started. Searching for 'TelosFocus'...")
    inlet = None
    
    while True:
        try:
            if inlet is None:
                if lsl_connected:
                    lsl_connected = False
                    await sio.emit('stream_status', {'connected': False})
                
                # Use to_thread for blocking resolution
                streams = await asyncio.to_thread(resolve_byprop, 'name', 'TelosFocus', timeout=1.0)
                if streams:
                    inlet = StreamInlet(streams[0])
                    lsl_connected = True
                    logger.info("✅ LSL Bridge: Connected to 'TelosFocus' stream.")
                    await sio.emit('stream_status', {'connected': True})
                else:
                    await asyncio.sleep(2.0)
                    continue
            
            # Use to_thread for blocking sample pull
            sample, timestamp = await asyncio.to_thread(inlet.pull_sample, timeout=0.1)
            if sample:
                focus_val = float(sample[0])
                # Emit to all browsers
                await sio.emit('focus_update', {'value': focus_val})
            else:
                # If we timeout too many times, we might have lost connection
                pass
                
        except Exception as e:
            logger.error(f"❌ LSL Bridge Error: {e}")
            inlet = None 
            lsl_connected = False
            await sio.emit('stream_status', {'connected': False})
            await asyncio.sleep(2.0)

# 4. Lifecycle Management
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing Showcase Application Subsystems...")
    bridge_task = asyncio.create_task(lsl_bridge())
    yield
    # Shutdown
    logger.info("Shutting down Application Subsystems...")
    bridge_task.cancel()
    try:
        await bridge_task
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=lifespan)
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
    # Inform the client about the current stream status immediately
    await sio.emit('stream_status', {'connected': lsl_connected}, to=sid)

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

if __name__ == "__main__":
    # Run on port 3000 as requested for the Showcase UI
    logger.info("Starting Uvicorn server on http://0.0.0.0:3000")
    uvicorn.run(socket_app, host="0.0.0.0", port=3000, log_level="info")
