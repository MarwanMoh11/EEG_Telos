import sys
import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel
from PyQt5.QtCore import QTimer
from pylsl import StreamInlet, resolve_byprop
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

class EEGVisualizer(QMainWindow):
    def __init__(self, inlet, channels=8, fs=250.0):
        super().__init__()
        self.inlet = inlet
        self.channels = channels
        self.fs = fs
        
        # We will display 5 seconds of data on the screen at a time
        self.window_size = int(5 * self.fs)
        
        # Buffer to hold the data for plotting: shape (channels, window_size)
        self.data_buffer = np.zeros((self.channels, self.window_size))
        
        # Channel Labels
        self.channel_names = ['Fz', 'C3', 'Cz', 'C4', 'Pz', 'PO7', 'Oz', 'PO8']
        
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle("Real-Time EEG LSL Stream (Unicorn)")
        self.resize(1000, 800)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # Add a title label
        title = QLabel(f"Connected to LSL Stream: {self.inlet.info().name()}")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # Create pyqtgraph plotting widget
        self.graphWidget = pg.PlotWidget()
        self.graphWidget.setBackground('k') # Black background
        self.graphWidget.showGrid(x=True, y=True, alpha=0.3)
        self.graphWidget.setLabel('bottom', "Time", units='s')
        self.graphWidget.setLabel('left', "Microvolts", units='µV')
        
        # We will stagger the 8 channels vertically so they don't overlap completely.
        # This offset is subtracted from each subsequent channel to visually stack them.
        self.vertical_offset = 200 
        
        layout.addWidget(self.graphWidget)
        
        # Create 8 plot lines (one for each channel)
        self.curves = []
        colors = ['#FF0000', '#00FF00', '#0000FF', '#FFFF00', '#FF00FF', '#00FFFF', '#FFA500', '#FFFFFF']
        
        for i in range(self.channels):
            pen = pg.mkPen(color=colors[i % len(colors)], width=1.5)
            curve = self.graphWidget.plot(pen=pen, name=self.channel_names[i])
            self.curves.append(curve)
            
        # Add a legend
        self.graphWidget.addLegend()
        for i, curve in enumerate(self.curves):
             self.graphWidget.plotItem.legend.addItem(curve, self.channel_names[i])
             
        # Setup a fast timer to pull new LSL data and update the plot 
        # (30 FPS = ~33ms)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(33) 
        
    def update_plot(self):
        # 1. Pull whatever new data is sitting in the LSL buffer
        # pull_chunk returns 'chunk' (list of lists) and 'timestamps'
        chunk, timestamps = self.inlet.pull_chunk(timeout=0.0)
        
        if timestamps:
            # Convert standard Python list to numpy array for fast math
            # Shape will be (samples_received, channels)
            new_data = np.array(chunk) 
            num_samples = new_data.shape[0]
            
            # 2. Shift the old data left and append the new data to the right
            if num_samples >= self.window_size:
                # Rare case: if we lagged so hard we got more than 5 seconds at once
                self.data_buffer = new_data[-self.window_size:, :].T 
            else:
                # Normal case: Roll buffer left by num_samples, then overwrite the end
                self.data_buffer = np.roll(self.data_buffer, -num_samples, axis=1)
                self.data_buffer[:, -num_samples:] = new_data.T
                
            # 3. Create the X-axis time vector (-5 seconds to 0)
            time_vector = np.linspace(-5, 0, self.window_size)
            
            # 4. Update the visual plot lines
            for i in range(self.channels):
                # Stagger the lines vertically using self.vertical_offset so they don't overlap
                plot_data = self.data_buffer[i, :] - (i * self.vertical_offset)
                self.curves[i].setData(time_vector, plot_data)

def main():
    logger.info("Looking for an EEG stream on the local network...")
    
    # Try specifically to find 'UnicornMint' first, or fallback to any 'EEG' type stream.
    streams = resolve_byprop('name', 'UnicornMint', timeout=2.0)
    if not streams:
        logger.info("Could not find 'UnicornMint', searching for ANY stream of type 'EEG'...")
        streams = resolve_byprop('type', 'EEG', timeout=5.0)
        
    if not streams:
        logger.error("No EEG stream found! Is main_linux.py actively running?")
        sys.exit(1)
        
    logger.info(f"Connecting to stream: {streams[0].name()}")
    inlet = StreamInlet(streams[0], max_buflen=360) # 360 second internal buffer just in case
    
    # Check stream info
    info = inlet.info()
    channels = info.channel_count()
    fs = info.nominal_srate()
    logger.info(f"Stream Info: {channels} channels at {fs}Hz")
    
    # Start the PyQt Application
    app = QApplication(sys.argv)
    
    # Use dark theme for standard widgets matching the black graph
    app.setStyle("Fusion")
    
    visualizer = EEGVisualizer(inlet=inlet, channels=channels, fs=fs)
    visualizer.show()
    
    logger.info("Starting real-time visualization loop. Close the window or press Ctrl+C to exit.")
    
    # Handle Ctrl+C gracefully in PyQt
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    # Execute the PyQt event loop
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
