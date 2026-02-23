# Telos Digital Twin: Neuro-Reflex Stack

A high-performance "Neural Reflex" system for Linux Mint, bridging BCI hardware with Generative AI reasoning.

## 🚀 Core Components

### 1. Neuro-Reflex Engine (`/neuro_reflex`)
The system's "Spinal Cord". 
- **Real-time Signal Processing**: 50Hz Notch (Egypt Grid) + 1-50Hz Bandpass.
- **Riemannian Classifier**: Interprets brain states using Covariance Manifolds.
- **Burnout Protocol**: Uses **Gemini 2.5 Flash Lite** to analyze fatigue and issue JSON commands.

### 2. Showcase Dashboard (`/showcase`)
A premium, non-technical interface for demonstration.
- **FastAPI Backend**: Bridges LSL brain data to WebSockets.
- **Glassmorphism UI**: Real-time Focus Gauges and Action Alerts.
- **Live Terminal**: Transparent view into the AI's reasoning process.

## 🛠️ Getting Started

### Installation
```bash
# Install core and showcase dependencies
pip install -r neuro_reflex/requirements.txt
pip install -r showcase/requirements.txt
```

### Configuration
1. Setup your `GEMINI_API_KEY` in `neuro_reflex/.env`.
2. Ensure you are in the `dialout` group for Bluetooth access.

### Execution
1. **Showcase UI**: `python3 showcase/backend.py` (Browse to http://localhost:3000)
2. **BCI Engine**: `python3 neuro_reflex/main.py` (Follow CLI Calibration)

---

## 📖 Complete Documentation
For detailed technical setup and troubleshooting, see **[neuro_reflex/DEPLOYMENT.md](neuro_reflex/DEPLOYMENT.md)**.

*Developed for the Telos Digital Twin Application.*
