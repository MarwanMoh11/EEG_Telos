# Neuro-Reflex Engine: Strategic Deployment Guide

This guide provides the sequence of operations to deploy the full Telos Neuro-Reflex stack: the **Engine** (core BCI logic) and the **Showcase Dashboard** (UI).

## 📊 Quick System Architecture
1. **Unicorn Headset** -> Bluetooth -> **Neuro-Reflex Engine** (Python)
2. **Neuro-Reflex Engine** -> LSL + Socket.IO -> **Showcase Backend** (FastAPI)
3. **Showcase Backend** -> WebSockets -> **Global UI** (Browser)

---

## 1. Prerequisites (Linux Mint)

### Hardware Permissions
Ensure your user can access the serial/bluetooth devices:
```bash
sudo usermod -a -G dialout $USER
# Log out and log back in for changes to apply.
```

### Environment Setup
We recommend separate environments or one master environment for the Telos root.
```bash
# From /home/marwan/Antigravity/EEG
python3 -m venv venv
source venv/bin/activate
pip install -r neuro_reflex/requirements.txt
pip install -r showcase/requirements.txt
```

---

## 2. Configuration & Secrets

### Neural Reasoning (Gemini)
1. Copy `neuro_reflex/.env.example` to `neuro_reflex/.env`.
2. Add your **GEMINI_API_KEY**.
3. (Optional) Adjust burnout thresholds in `neuro_reflex/reasoning.py`.

---

## 3. Deployment Sequence

### Step 1: Launch the Showcase Dashboard
The dashboard must start first on port 3000 to listen for the engine.
```bash
cd showcase
python3 backend.py
```
*   **Access**: http://localhost:3000

### Step 2: Launch the Neuro-Reflex Engine
In a separate terminal:
```bash
cd neuro_reflex
python3 main.py
```
*   **Calibration**: Follow the CLI prompts for the **10s Rest** and **10s Focus** phases.
*   **Arming**: Once "System Armed" appears, the signals will flow to the UI.

---

## 4. Operational Testing

| Feature | Verification Method |
|---------|---------------------|
| **EEG Stream** | Open Dashboard -> Gauge should respond to activity. |
| **LSL Bridge** | Run `python3 receiver.py` in root -> Look for `TelosFocus`. |
| **AI Reflex** | Wait 5 mins or lower thresholds in `reasoning.py` -> Card appears in UI. |
| **SocketIO** | Engine console shows "Socket.IO Client connected". |

---

## 5. Troubleshooting
- **Device Busy**: Ensure no other Brainflow/Unicorn scripts are running. Unplug/Replug the Bluetooth dongle if necessary.
- **UI 404/Connection Error**: Ensure `backend.py` is running on port 3000 before starting `main.py`.
