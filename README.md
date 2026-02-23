# Unicorn Hybrid Black - LSL Bridge (Linux Edition)

This repository contains a robust, production-ready pipeline for connecting the **g.tec Unicorn Hybrid Black** EEG headset to a Linux Mint / Ubuntu system via Bluetooth, processing the raw signals in real-time, and broadcasting them over the local network using the **Lab Streaming Layer (LSL)**.

It utilizes [BrainFlow](https://brainflow.org/) as the backend driver wrapper, bypassing the need for proprietary Windows-only SDKs.

## 🧠 Features
- **Auto-Discovery:** Automatically scans for and connects to the Unicorn headset via Bluetooth.
- **Real-Time Signal Processing:** 
  - `1Hz Highpass Butterworth Filter`: Removes DC offset and slow drift.
  - `50Hz Lowpass Butterworth Filter`: Cleans high-frequency noise.
  - `50Hz & 100Hz IIR Notch Filters`: Aggressively targets powerline noise (configured for Egypt/EU 50Hz mains).
- **Extensible Data:** Streams 15 Channels (8 EEG, 3 Accelerometer, 3 Gyroscope, 1 Battery).
- **Proof-of-Concept Apps:** Includes scripts for CSV recording, live FFT visualizers, and EMG jaw-clench detection.

---

## 🛠️ System Prerequisites (Linux MINT/Ubuntu)

Before running the python scripts, your Linux system needs permission to access the Bluetooth serial ports.

1. **Add your user to the `dialout` and `bluetooth` groups:**
   Open a terminal and run the following command:
   ```bash
   sudo usermod -a -G dialout,bluetooth $USER
   ```
2. **RESTART YOUR COMPUTER:** You **must** reboot your computer for the group permission changes to take effect!
3. **Turn Bluetooth On:** Ensure your laptop's Bluetooth adapter is powered on. You can do this via the system tray or by running `bluetoothctl power on`.

---

## 🎧 Hardware Guide: Operating the Unicorn Headset

The Unicorn headset has a single button and a status LED. Understanding the LED colors is crucial for a successful connection.

1. **To Turn On:** Press and hold the power button for ~2 seconds.
2. **To Turn Off:** Press and hold the power button until the LED turns off.

### LED Status Meanings:
*   🔵 **Blinking Blue:** The device is powered ON, but it is **NOT connected** to your computer. It is waiting for the Python script to find it.
*   🔵 **Solid Blue:** The device is **successfully connected** via Bluetooth and is ready to stream.
*   🔴 **Solid Red:** The battery is empty and needs to be charged via USB.
*   🟢 **Solid Green:** The device is plugged into USB and is actively charging.
*   🟢 **Blinking Green:** The device is plugged into USB and is fully charged.

*(Note: The headset **cannot** be used to stream data while it is plugged into a USB cable. It must be running on battery to stream over Bluetooth).*

---

## 🚀 Setup & Installation

Clone the repository and install the required Python packages into a virtual environment.

```bash
# 1. Clone the repo
git clone https://github.com/MarwanMoh11/EEG_Telos.git
cd EEG_Telos

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## 🏃‍♂️ How to Run the Pipeline

The pipeline consists of one **Broadcaster** script (which physically connects to the headset) and several **Consumer** scripts (which listen to the broadcaster over the network).

### Step 1: Start the Broadcaster
You must ALWAYS run this script first. It acts as the engine for the entire pipeline.

1. **Unplug** the headset from USB and turn it **ON** (LED should blink blue).
2. Open a terminal and run:
   ```bash
   source venv/bin/activate
   python main_linux.py
   ```
3. When prompted for `libunicorn.so` and the Serial Number, you can simply **Press Enter twice** to let BrainFlow auto-discover the headset.
4. Wait for the terminal to print `Data streaming started.`. The headset LED should now be **Solid Blue**.

*Leave this terminal running in the background.*

### Step 2: Use the Data (Consumer Scripts)
While `main_linux.py` is running, you can open **new terminal windows** to run any of the consumer scripts. You can run multiple consumers at the same time!

**(Remember to run `source venv/bin/activate` in every new terminal before running a python script).**

#### 📹 Option A: The Real-Time Visualizer
Displays a scrolling, real-time graph of the 8 filtered EEG channels.
```bash
python receiver.py
```

#### 📊 Option B: The CSV Recorder (For Machine Learning)
Losslessly records all 15 channels (EEG + Motion + Battery) to a timestamped `.csv` file for offline analysis or AI training.
```bash
python record_csv.py
```
*(Press `Ctrl+C` in that terminal to safely stop recording and save the file).*

#### 🧠 Option C: The FFT Spectral Visualizer
Calculates the Power Spectral Density (PSD) using a Fast Fourier Transform. Useful for seeing brain frequencies like Alpha (8-13Hz) when the user closes their eyes, or Beta (13-30Hz) when focusing.
```bash
python fft_visualizer.py
```

#### 🤖 Option D: The AI Jaw Clench Detector
A terminal-based Proof-of-Concept for "Live BCI". It analyzes the variance of the EEG wave chunks in real-time. If the wearer clenches their jaw, the massive EMG muscle artifact triggers the script to print a red warning.
```bash
python jaw_clench_detector.py
```
