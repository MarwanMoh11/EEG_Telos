const socket = io();

// UI Elements: Navigation & Metrics
const lslStatusEl = document.getElementById('lsl-status');
const recalibBtn = document.getElementById('recalib-btn');

// UI Elements: Calibration Overlay
const calibOverlay = document.getElementById('calib-overlay');
const startCalibBtn = document.getElementById('start-calib-btn');
const calibContent = document.getElementById('calib-content');
const calibActive = document.getElementById('calib-active');
const phaseNameEl = document.getElementById('phase-name');
const calibTimerEl = document.getElementById('calib-timer');
const calibProgressBar = document.getElementById('calib-progress-bar');
const phaseInstructionEl = document.getElementById('phase-instruction');
const signalStatusEl = document.getElementById('signal-status');

// UI Elements: Dashboard
const focusValEl = document.getElementById('focus-val');
const gaugePath = document.getElementById('gauge-path');
const fatigueMinsEl = document.getElementById('fatigue-mins');
const fatigueBar = document.getElementById('fatigue-bar');
const reflexStage = document.getElementById('reflex-stage');
const terminalEl = document.getElementById('terminal');

// State
let isCalibrating = false;
let currentFocus = 0.5;
let continuousLoad = 0.0;
let timerInterval = null; // Single global interval to prevent clashing

// 1. Calibration Logic
startCalibBtn.addEventListener('click', () => {
    socket.emit('request_calibration', {});
    showCalibrationPhase('INIT');
    log('Calibration requested. Communicating with engine...', 'sys');
});

recalibBtn.addEventListener('click', () => {
    socket.emit('request_calibration', {});
    calibOverlay.classList.remove('hidden');
    showCalibrationPhase('INIT');
});

socket.on('stream_status', (data) => {
    const isConnected = data.connected;

    if (isConnected) {
        startCalibBtn.disabled = false;
        startCalibBtn.innerText = 'Start Calibration';
        signalStatusEl.classList.add('hidden');
        lslStatusEl.innerText = 'READY';
        lslStatusEl.classList.remove('dim', 'red');
        lslStatusEl.classList.add('green');
        log('Neural Stream Detected. System Armed.', 'sys');
    } else {
        startCalibBtn.disabled = true;
        startCalibBtn.innerText = 'Signal Lost';
        signalStatusEl.classList.remove('hidden');
        lslStatusEl.innerText = 'OFFLINE';
        lslStatusEl.classList.remove('dim', 'green');
        lslStatusEl.classList.add('red');
        log('Neural Stream Lost. Please check device pairing.', 'sys');
    }
});

socket.on('calib_status', (data) => {
    const state = data.state;
    console.log("Calibration event received:", state, data);

    if (state === 'PREP') {
        showCalibrationPhase('INIT');
        startTimer(data.countdown, 'PREPARING', 'Get ready! Calibration starting soon...');
    } else if (state === 'REST') {
        startTimer(data.duration, 'REST', 'Keep your eyes closed and body still.');
        log('Recording REST baseline initialized.', 'eng');
    } else if (state === 'PREP_FOCUS') {
        startTimer(data.countdown, 'SWITCHING', 'Get ready for active focus phase...');
    } else if (state === 'FOCUS') {
        startTimer(data.duration, 'FOCUS', 'Focus intensely on math or a fixed point.');
        log('Recording ACTIVE FOCUS initialized.', 'eng');
    } else if (state === 'DONE') {
        if (timerInterval) clearInterval(timerInterval);
        calibOverlay.classList.add('hidden');
        log('Neural Alignment Complete. Classifier Integrated.', 'sys');
        lslStatusEl.innerText = 'CALIBRATED';
        lslStatusEl.classList.remove('dim');
        lslStatusEl.classList.add('green');
    }
});

function showCalibrationPhase(phase) {
    if (phase === 'INIT') {
        calibContent.classList.add('hidden');
        calibActive.classList.remove('hidden');
    }
}

function startTimer(duration, phase, task) {
    if (timerInterval) clearInterval(timerInterval);

    phaseNameEl.innerText = phase;
    phaseInstructionEl.innerText = task;

    let timeLeft = duration;
    calibTimerEl.innerText = timeLeft;

    // Reset progress bar
    calibProgressBar.style.transition = 'none';
    calibProgressBar.style.width = '0%';

    setTimeout(() => {
        calibProgressBar.style.transition = `width ${duration}s linear`;
        calibProgressBar.style.width = '100%';
    }, 50);

    timerInterval = setInterval(() => {
        timeLeft--;
        if (timeLeft >= 0) {
            calibTimerEl.innerText = timeLeft;
        }
        if (timeLeft <= 0) {
            clearInterval(timerInterval);
        }
    }, 1000);
}

// 2. Real-time Focus Data
socket.on('focus_update', (data) => {
    const val = data.value;
    const percent = Math.round(val * 100);

    focusValEl.innerText = percent;

    // Gauge Animation (SVG Dashoffset)
    const offset = 283 - (val * 283);
    gaugePath.style.strokeDashoffset = offset;

    // Update State
    currentFocus = val;
    if (val > 0.6) {
        continuousLoad += (1 / 60); // approx logic increment
        updateFatigueUI();
    } else {
        continuousLoad = Math.max(0, continuousLoad - (0.5 / 60)); // slow recovery
        updateFatigueUI();
    }

    if (percent % 10 === 0) {
        log(`Inference: Focus probability shifted to ${percent}%`, 'eng');
    }
});

function updateFatigueUI() {
    fatigueMinsEl.innerText = `${continuousLoad.toFixed(1)}m`;
    const progress = Math.min(100, (continuousLoad / 20) * 100); // 20m threshold
    fatigueBar.style.width = `${progress}%`;
}

// 3. AI Actions
socket.on('ui_action', (data) => {
    const action = data.action;
    const reason = data.reason_triggered || "Periodic burnout scan.";

    reflexStage.innerHTML = `
        <div class="action-card ${action}">
            <h4>${action.replace('_', ' ')}</h4>
            <p>${reason}</p>
        </div>
    `;

    log(`Reasoning: [${action.toUpperCase()}] triggered by subsystem.`, 'ai');
});

// 4. Utils
function log(msg, type) {
    const time = new Date().toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const line = document.createElement('div');
    line.className = `line ${type}`;
    line.innerText = `[${time}] ${msg}`;
    terminalEl.appendChild(line);
    terminalEl.scrollTop = terminalEl.scrollHeight;

    if (terminalEl.children.length > 30) terminalEl.removeChild(terminalEl.firstChild);
}

// Auto-show calibration if not calibrated
setTimeout(() => {
    if (lslStatusEl.innerText !== 'CALIBRATED') {
        calibOverlay.classList.remove('hidden');
    }
}, 1000);
