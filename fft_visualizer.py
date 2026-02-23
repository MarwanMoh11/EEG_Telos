import sys
import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt5.QtCore import QTimer
from scipy.signal import welch
from pylsl import StreamInlet, resolve_byprop
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

class FFTVisualizer(QMainWindow):
    def __init__(self, inlet, channels=8, fs=250.0):
        super().__init__()
        self.inlet = inlet
        self.channels = channels
        self.fs = fs
        
        # 2 seconds of data for FFT calculation provides 0.5Hz frequency resolution
        self.window_size = int(2.0 * self.fs)
        self.data_buffer = np.zeros((self.channels, self.window_size))
        
        self.channel_names = ['Fz', 'C3', 'Cz', 'C4', 'Pz', 'PO7', 'Oz', 'PO8']
        
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle("Real-Time EEG Frequency Spectrum (Alpha/Beta Waves)")
        self.resize(1000, 600)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        self.graphWidget = pg.PlotWidget()
        self.graphWidget.setBackground('k')
        self.graphWidget.showGrid(x=True, y=True, alpha=0.3)
        self.graphWidget.setLabel('bottom', "Frequency", units='Hz')
        self.graphWidget.setLabel('left', "Power Spectral Density", units='uV^2/Hz')
        self.graphWidget.setLogMode(x=False, y=True) # Log Y axis makes EEG peaks more visible
        
        # Only view 1Hz to 50Hz (since we low passed at 50Hz)
        self.graphWidget.setXRange(1, 50)
        
        layout.addWidget(self.graphWidget)
        
        self.curves = []
        colors = ['#FF0000', '#00FF00', '#0000FF', '#FFFF00', '#FF00FF', '#00FFFF', '#FFA500', '#FFFFFF']
        
        for i in range(self.channels):
            pen = pg.mkPen(color=colors[i % len(colors)], width=2)
            curve = self.graphWidget.plot(pen=pen, name=self.channel_names[i])
            self.curves.append(curve)
            
        self.graphWidget.addLegend()
        
        # Alpha Band (8-13Hz) Highlight
        self.alpha_region = pg.LinearRegionItem([8, 13], brush=pg.mkBrush(0, 255, 0, 30), movable=False)
        self.graphWidget.addItem(self.alpha_region)
        
        # Beta Band (13-30Hz) Highlight
        self.beta_region = pg.LinearRegionItem([13, 30], brush=pg.mkBrush(0, 0, 255, 30), movable=False)
        self.graphWidget.addItem(self.beta_region)
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(100) # Update FFT 10 times a second
        
    def update_plot(self):
        chunk, timestamps = self.inlet.pull_chunk(timeout=0.0)
        
        if timestamps:
            new_data = np.array(chunk) 
            eeg_extract = new_data[:, :self.channels]
            num_samples = eeg_extract.shape[0]
            
            if num_samples >= self.window_size:
                self.data_buffer = eeg_extract[-self.window_size:, :].T 
            else:
                self.data_buffer = np.roll(self.data_buffer, -num_samples, axis=1)
                self.data_buffer[:, -num_samples:] = eeg_extract.T
                
            # Compute FFT using Welch's method for each channel
            for i in range(self.channels):
                freqs, psd = welch(self.data_buffer[i, :], fs=self.fs, nperseg=self.fs)
                
                # Prevent log(0)
                psd = np.clip(psd, 1e-12, None)
                
                # Set smoothed PSd line
                self.curves[i].setData(freqs, psd)

def main():
    logger.info("Starting Spectral Analyzer...")
    streams = resolve_byprop('name', 'UnicornMint', timeout=5.0)
    if not streams:
        logger.error("No EEG stream found! Run main_linux.py first.")
        sys.exit(1)
        
    inlet = StreamInlet(streams[0], max_buflen=5)
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    visualizer = FFTVisualizer(inlet=inlet, channels=8, fs=250.0)
    visualizer.show()
    
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
