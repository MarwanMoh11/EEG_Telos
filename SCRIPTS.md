# EEG Project: Running the Scripts

This guide provides instructions for running the various EEG-related scripts in the repository.

## Prerequisites

1.  **Virtual Environment**: Ensure you have activated the virtual environment:
    ```bash
    source venv/bin/activate
    ```
2.  **LSL Bridge**: Most scripts require an active Lab Streaming Layer (LSL) stream. Start the bridge first (in a separate terminal):
    ```bash
    # From the ROOT directory:
    python3 main.py
    ```
    *Note: If you are asked for a serial number, you can press Enter for auto-discovery.*

---

## 1. Channel Time-Series Visualizer
A PyQt-based graphical visualizer showing real-time raw EEG waveforms for 8 channels. This shows the actual "brain waves" as they happen.

**Run command:**
```bash
python3 receiver.py
```

## 2. Jaw Clench Detector
A terminal-based visualizer that detects when you clench your jaw by monitoring signal variance.

**Run command:**
```bash
python3 jaw_clench_detector.py
```
*   **Relaxed**: Shows a green bar.
*   **Clench**: Shows a yellow/red alert with amplitude in microvolts (uV).

## 3. Spectral (FFT) Visualizer
A PyQt-based graphical visualizer showing real-time Alpha and Beta waves across 8 EEG channels.

**Run command:**
```bash
python3 fft_visualizer.py
```

## 4. Neuro-Reflex Application (Full Pipeline)
A more complex application integrating classification and reasoning.

**Run command:**
```bash
cd neuro_reflex
python3 main.py
```

## 5. Web Showcase Dashboard
A real-time web interface for monitoring focus and system status.

**Step 1: Start the backend**
```bash
cd showcase
python3 backend.py
```
**Step 2: Access the UI**
Open `http://localhost:3000` in your browser.

*Note: The Engine (`neuro_reflex/main.py`) now supports **LSL Fallback Mode**. If the LSL bridge (`main.py`) is already running, the Engine will automatically detect and use its data stream instead of trying to connect to the Bluetooth device twice. This allows you to run both at the same time!*

---

## Full Frontend & AI Test (Recommended)

To see the dashboard **actually changing** with your brain focus (not just raw noise), follow these exactly:

### Terminal 1: The Bridge
```bash
# In Root directory
source venv/bin/activate
python3 main.py
```

### Terminal 2: The AI Engine (Processes the focus)
```bash
# In neuro_reflex directory
source ../venv/bin/activate
python3 main.py
```
*   **Wait** for the prompt and enter your Serial Number.
*   **Don't press start calibration yet** on the website.

### Terminal 3: The Web Dashboard (Shows the data)
```bash
# In showcase directory
source ../venv/bin/activate
python3 backend.py
```

### Terminal 4: The Browser
1.  Go to `http://localhost:3000`.
2.  The dashboard should say **"READY"** in green.
3.  Click **"Start Calibration"**.
4.  **RELAX (10s)** when it says "REST".
5.  **CONCENTRATE (10s)** when it says "FOCUS" (math, counting, or focus on a point).
6.  Once done, the gauge will move based on how much you focus.

---

## How to Validate if the Device is Working correctly

Once you have `receiver.py` (Time-Series) or `fft_visualizer.py` (FFT) running, perform these checks to ensure you have a clean signal:

### 1. The Blink Test (Frontal Sensitivity)
*   **Action**: Blink your eyes firmly.
*   **Result in `receiver.py`**: You should see sharp, vertical spikes on the **Fz** channel (top channel). If you see these spikes, the headset is correctly capturing muscle/electrical changes from the front.

### 2. The Clench Test (Broadband Noise)
*   **Action**: Clench your jaw tightly.
*   **Result in `receiver.py`**: The signal should explode into massive, thick noise across all 8 channels.
*   **Result in `jaw_clench_detector.py`**: The bar should turn **RED** and report values > 200uV.

### 3. The Alpha Wave Test (Neural Validation)
*   **Action**: Relax and close your eyes for 5-10 seconds while keeping the headset on.
*   **Result in `fft_visualizer.py`**: You should see a distinct "hump" or peak appearing in the **8-13Hz (Alpha)** range (shaded green). When you open your eyes, this peak should disappear. This is the gold standard for verifying real EEG data.

### 4. Noise Checklist
*   **Flat Lines**: If a channel is a perfectly flat line at 0, it has poor contact. Apply more gel or adjust the electrode.
*   **Large Sine Waves (50Hz)**: If you see huge, consistent oscillations, it's electrical interference from the room's power grid. Ensure the LSL bridge (`main.py`) notch filter is active.

---

## Troubleshooting

-   **"No stream found!"**: Make sure `python3 main.py` is running in another terminal.
-   **"No such file or directory"**: Always run scripts from the directory where they are located. Root scripts should be run from the root; directory-specific scripts from their respective folders.
-   **Permission Denied (Serial)**: Ensure your user is in the `dialout` group: `sudo usermod -a -G dialout $USER` (requires logout/restart).
