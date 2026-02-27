# Telos Digital Twin: Neuro-Reflex Stack

A high-performance "Neural Reflex" system for Linux Mint, bridging BCI hardware with Generative AI reasoning.

## 🚀 Core Components

### 1. Telos Command Center (`/showcase`)
The central unified dashboard for operating the EEG pipeline.
- **Embedded Generative AI**: Uses `backend.py` to manage all data flows.
- **Zero-CLI Interface**: Toggle between real Unicorn headset data and a built-in synthetic signal generator directly from the browser.
- **Real-Time Visualization**: Canvas-based EEG waveforms, FFT frequency spectrum, and automatic artifact detection (blinks, jaw clenches).

### 2. Neuro-Reflex Engine (`/neuro_reflex`)
The system's underlying "Spinal Cord" (managed automatically or run explicitly for advanced logging).
- **Real-time Signal Processing**: 50Hz Notch (Egypt Grid) + 1-50Hz Bandpass.
- **Riemannian Classifier**: Interprets brain states using Covariance Manifolds.
- **Burnout Protocol**: Uses **Gemini 2.5 Flash Lite** to analyze fatigue and issue JSON commands.

## 🛠️ Getting Started

### Installation
You need `scipy` for the new backend FFT computations.
```bash
# Enter the showcase directory
cd showcase
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
pip install scipy
```

### Configuration
1. Setup your `GEMINI_API_KEY` in `neuro_reflex/.env`.
2. Ensure you are in the `dialout` group for Bluetooth access.

### Execution

To launch the unified, no-CLI dashboard:
```bash
# Inside the showcase venv
python3 backend.py
```
Then, open your browser to **http://localhost:3000**. The dashboard will start in **Synthetic** mode automatically. You can toggle to **Device** mode via the top navigation bar when your Unicorn headset is connected.

---

## 📖 Complete Documentation
For detailed technical setup and troubleshooting, see **[neuro_reflex/DEPLOYMENT.md](neuro_reflex/DEPLOYMENT.md)**.

*Developed for the Telos Digital Twin Application.*
