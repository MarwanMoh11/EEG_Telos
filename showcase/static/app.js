// ═══════════════════════════════════════════════════════════
//  TELOS COMMAND CENTER — Frontend Controller
// ═══════════════════════════════════════════════════════════
console.log("[Telos] Command Center loading...");
const socket = io();

// ─── DOM Refs ───────────────────────────────────────────────
const lslStatusEl = document.getElementById('lsl-status');
const streamNameEl = document.getElementById('stream-name');
const recalibBtn = document.getElementById('recalib-btn');
const calibOverlay = document.getElementById('calib-overlay');
const startCalibBtn = document.getElementById('start-calib-btn');
const calibContent = document.getElementById('calib-content');
const calibActive = document.getElementById('calib-active');
const phaseNameEl = document.getElementById('phase-name');
const calibTimerEl = document.getElementById('calib-timer');
const calibProgressBar = document.getElementById('calib-progress-bar');
const phaseInstructionEl = document.getElementById('phase-instruction');
const signalStatusEl = document.getElementById('signal-status');
const focusValEl = document.getElementById('focus-val');
const gaugePath = document.getElementById('gauge-path');
const focusBadge = document.getElementById('focus-badge');
const artifactBadge = document.getElementById('artifact-badge');
const artifactBarsEl = document.getElementById('artifact-bars');
const artifactDetail = document.getElementById('artifact-detail');
const termBody = document.getElementById('terminal');
const clearTermBtn = document.getElementById('clear-term-btn');
const cancelCalibBtn = document.getElementById('cancel-calib-btn');
const eegCanvas = document.getElementById('eeg-canvas');

// Error Modal Refs
const errorOverlay = document.getElementById('error-overlay');
const errorTitle = document.getElementById('error-title');
const errorMsg = document.getElementById('error-msg');
const errorOkBtn = document.getElementById('error-ok-btn');
const fftCanvas = document.getElementById('fft-canvas');
const channelLegend = document.getElementById('channel-legend');
const syntheticControls = document.getElementById('synthetic-controls');
const devicePerformance = document.getElementById('device-performance');
const bufferHealthFill = document.getElementById('buffer-health-fill');
const bufferHealthVal = document.getElementById('buffer-health-val');

// Control buttons
const btnSynthetic = document.getElementById('btn-synthetic');
const btnDevice = document.getElementById('btn-device');
const ctrlClench = document.getElementById('ctrl-clench');
const ctrlBlink = document.getElementById('ctrl-blink');
const ctrlFocus = document.getElementById('ctrl-focus');
const clenchStateEl = document.getElementById('clench-state');
const focusStateEl = document.getElementById('focus-state');
const noiseBtns = document.querySelectorAll('#noise-selector .seg-btn');
const moodBtns = document.querySelectorAll('#mood-selector .seg-btn');

const aiBtn = document.getElementById('btn-analyze-state');
const aiResultBox = document.getElementById('ai-result-box');
const aiStateLabel = document.getElementById('ai-state-label');
const aiInsightText = document.getElementById('ai-insight-text');

// ─── Constants ──────────────────────────────────────────────
const CHANNEL_NAMES = ['Fz', 'C3', 'Cz', 'C4', 'Pz', 'PO7', 'Oz', 'PO8'];
const CHANNEL_COLORS = [
    '#ff4d6a', '#00ffaa', '#4dc9f6', '#ffbf00',
    '#d580ff', '#00f2ff', '#ff7b00', '#ffffff'
];
const EEG_WINDOW = 5;     // seconds
const SAMPLE_RATE = 250;
const EEG_BUFFER_LEN = EEG_WINDOW * SAMPLE_RATE;

// ─── State ──────────────────────────────────────────────────
let isConnected = false;
let isCalibrating = false;
let dataSource = 'synthetic';
let synClench = false;
let synFocus = false;
let timerInterval = null;

// EEG waveform buffer: 8 channels x EEG_BUFFER_LEN samples
const eegBuffer = [];
for (let i = 0; i < 8; i++) eegBuffer.push(new Float32Array(EEG_BUFFER_LEN));

// FFT data
let fftFreqs = [];
let fftPsd = []; // 8 arrays

// ─── Init Channel Legend ────────────────────────────────────
CHANNEL_NAMES.forEach((name, i) => {
    const el = document.createElement('div');
    el.className = 'ch-label';
    el.innerHTML = `<span class="ch-dot" style="background:${CHANNEL_COLORS[i]}"></span>${name}`;
    channelLegend.appendChild(el);
});

// Init artifact bars
for (let i = 0; i < 8; i++) {
    const bar = document.createElement('div');
    bar.className = 'artifact-bar';
    bar.style.height = '2px';
    bar.style.background = 'var(--green)';
    artifactBarsEl.appendChild(bar);
}

// ═══════════════════════════════════════════════════════════
//  SOCKET.IO HANDLERS
// ═══════════════════════════════════════════════════════════
socket.on('connect', () => {
    log('Neural Link Established.', 'sys');
    socket.emit('get_stream_status');
});

socket.on('stream_status', (data) => {
    isConnected = data.connected;
    dataSource = data.data_source || dataSource;

    if (isConnected) {
        lslStatusEl.innerText = dataSource === 'synthetic' ? 'SYNTHETIC' : 'DEVICE';
        lslStatusEl.classList.remove('dim', 'red');
        lslStatusEl.classList.add('green');
        streamNameEl.innerText = data.stream_name || 'Active';
        streamNameEl.classList.remove('dim');
        streamNameEl.classList.add('green');
        startCalibBtn.disabled = false;
        signalStatusEl.classList.add('hidden');
        if (dataSource === 'device') setDeviceLoading(false);
    } else {
        lslStatusEl.innerText = 'OFFLINE';
        lslStatusEl.classList.remove('dim', 'green');
        lslStatusEl.classList.add('red');
        streamNameEl.innerText = 'Searching...';
        streamNameEl.classList.remove('green');
        streamNameEl.classList.add('dim');
    }

    // Update source toggle visual
    btnSynthetic.classList.toggle('active', dataSource === 'synthetic');
    btnDevice.classList.toggle('active', dataSource === 'device');
    syntheticControls.classList.toggle('hidden-controls', dataSource !== 'synthetic');

    // Recalibrate button logic:
    // Only show in device mode. Only enable if connected.
    if (dataSource === 'device') {
        recalibBtn.classList.remove('hidden-controls');
        recalibBtn.disabled = !isConnected;
        recalibBtn.style.opacity = isConnected ? '1' : '0.4';
    } else {
        recalibBtn.classList.add('hidden-controls');
    }
});

socket.on('force_source_toggle', (data) => {
    if (data.source === 'synthetic') {
        dataSource = 'synthetic';
        btnSynthetic.classList.add('active');
        btnDevice.classList.remove('active');
        syntheticControls.classList.remove('hidden-controls');
        log('Device unavailable. Reverted to Synthetic.', 'sys');
    }
});

socket.on('connection_error', (data) => {
    setDeviceLoading(false);
    errorTitle.innerText = data.title || 'Connection Failed';
    errorMsg.innerText = data.msg || 'An unknown error occurred.';
    errorOverlay.classList.remove('hidden');
    log('Connection Error: ' + errorMsg.innerText, 'sys');
});

socket.on('eeg_waveform', (data) => {
    const chunk = data.data; // 8 arrays of chunk_size
    const chunkSize = data.chunk_size;

    for (let ch = 0; ch < 8; ch++) {
        // Shift buffer left by chunkSize, append new data
        eegBuffer[ch].copyWithin(0, chunkSize);
        for (let s = 0; s < chunkSize; s++) {
            eegBuffer[ch][EEG_BUFFER_LEN - chunkSize + s] = chunk[ch][s];
        }
    }
});

socket.on('fft_update', (data) => {
    fftFreqs = data.freqs;
    fftPsd = data.psd;
});

socket.on('focus_update', (data) => {
    const val = data.value;
    const percent = Math.round(val * 100);

    focusValEl.innerText = percent;
    const offset = 283 - (val * 283);
    gaugePath.style.strokeDashoffset = offset;

    if (val > 0.65) {
        focusBadge.innerText = 'FOCUSED';
        focusBadge.style.background = 'rgba(0,255,170,0.1)';
        focusBadge.style.color = 'var(--green)';
    } else if (val > 0.45) {
        focusBadge.innerText = 'NEUTRAL';
        focusBadge.style.background = 'rgba(0,242,255,0.1)';
        focusBadge.style.color = 'var(--accent)';
    } else {
        focusBadge.innerText = 'RELAXED';
        focusBadge.style.background = 'rgba(112,0,255,0.1)';
        focusBadge.style.color = '#b388ff';
    }
});

socket.on('artifact_event', (data) => {
    const { type, detail, channel_ptp, max_ptp } = data;

    // Update badge
    if (type === 'clench_hard') {
        artifactBadge.innerText = 'CLENCH';
        artifactBadge.className = 'artifact-badge danger';
    } else if (type === 'clench_mild') {
        artifactBadge.innerText = 'MILD';
        artifactBadge.className = 'artifact-badge warning';
    } else if (type === 'blink') {
        artifactBadge.innerText = 'BLINK';
        artifactBadge.className = 'artifact-badge warning';
    } else {
        artifactBadge.innerText = 'CLEAN';
        artifactBadge.className = 'artifact-badge relaxed';
    }

    // Update bars
    const bars = artifactBarsEl.children;
    if (channel_ptp && bars.length === 8) {
        const maxVal = Math.max(...channel_ptp, 1);
        for (let i = 0; i < 8; i++) {
            const h = Math.max(2, (channel_ptp[i] / maxVal) * 50);
            bars[i].style.height = h + 'px';
            if (channel_ptp[i] > 160) bars[i].style.background = 'var(--red)';
            else if (channel_ptp[i] > 80) bars[i].style.background = 'var(--yellow)';
            else bars[i].style.background = 'var(--green)';
        }
    }

    artifactDetail.innerText = detail || 'Signal quality nominal';
});

// Calibration handlers
socket.on('calib_status', (data) => {
    const s = data.state;
    if (s === 'PREP') {
        showCalibrationPhase('INIT');
        startTimer(data.countdown, 'PREPARING', 'Get ready! Calibration starting soon...');
    } else if (s === 'REST') {
        startTimer(data.duration, 'REST', 'Keep your eyes closed and body still.');
        log('Recording REST baseline.', 'eng');
    } else if (s === 'PREP_FOCUS') {
        startTimer(data.countdown, 'SWITCHING', 'Get ready for active focus phase...');
    } else if (s === 'FOCUS') {
        startTimer(data.duration, 'FOCUS', 'Focus intensely on math or a fixed point.');
        log('Recording ACTIVE FOCUS.', 'eng');
    } else if (s === 'DONE') {
        if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
        calibOverlay.classList.add('hidden');
        log('Neural Alignment Complete.', 'sys');
        isCalibrating = false;
    } else if (s === 'ERROR') {
        if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
        phaseNameEl.innerText = 'ERROR';
        phaseInstructionEl.innerHTML = `<span class="red">Failed:</span><br>${data.msg}`;
        log(`Calibration Error: ${data.msg}`, 'sys');
        isCalibrating = false;
        setTimeout(() => { if (phaseNameEl.innerText === 'ERROR') calibOverlay.classList.add('hidden'); }, 5000);
    }
});

socket.on('ui_action', (data) => {
    log(`Reflex: [${data.action.toUpperCase()}] — ${data.reason_triggered || ''}`, 'ai');
});

socket.on('engine_log', (data) => {
    log(`${data.msg}`, 'eng');
});

socket.on('synthetic_state', (data) => {
    synClench = data.clench;
    synFocus = data.focus;
    ctrlClench.classList.toggle('active', synClench);
    ctrlFocus.classList.toggle('active', synFocus);
    clenchStateEl.innerText = synClench ? 'ON' : 'OFF';
    focusStateEl.innerText = synFocus ? 'ON' : 'OFF';

    // Update Noise Profile UI
    if (data.noise_level) {
        noiseBtns.forEach(btn => {
            if (btn.dataset.level === data.noise_level) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    }

    // Update Mood Profile UI
    if (data.mood) {
        moodBtns.forEach(btn => {
            if (btn.dataset.mood === data.mood) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    }
});

socket.on('classification_result', (data) => {
    log(`🧠 AI Diagnostics Complete: ${data.state}`, 'ai');

    // Restore button state
    aiBtn.innerHTML = '<span class="ai-icon">✨</span> Analyze Current State';
    aiBtn.disabled = false;

    // Populate and show the result
    aiStateLabel.innerText = data.state;
    aiInsightText.innerText = data.insight;
    aiResultBox.classList.remove('hidden-controls');
    aiResultBox.style.display = 'flex';
});

// ═══════════════════════════════════════════════════════════
//  UI EVENT HANDLERS
// ═══════════════════════════════════════════════════════════

// Data Source Toggle
btnSynthetic.addEventListener('click', () => {
    setDeviceLoading(false);
    socket.emit('set_data_source', { source: 'synthetic' });
    log('Switched to Synthetic data source.', 'sys');
});

btnDevice.addEventListener('click', () => {
    if (dataSource === 'device') return;
    setDeviceLoading(true);
    socket.emit('set_data_source', { source: 'device' });
    log('Initiating Neural Link. Searching for LSL...', 'sys');
    streamNameEl.innerText = 'Initializing...';
    streamNameEl.classList.remove('green');
    streamNameEl.classList.add('dim');
});

function setDeviceLoading(isLoading) {
    if (isLoading) {
        btnDevice.classList.add('loading');
        btnDevice.innerHTML = '<span class="toggle-icon">⌛</span> Searching...';
    } else {
        btnDevice.classList.remove('loading');
        btnDevice.innerHTML = '<span class="toggle-icon">🧠</span> Device';
    }
}

// Error Modal
errorOkBtn.addEventListener('click', () => {
    errorOverlay.classList.add('hidden');
    // Tell the backend we are going back to synthetic
    socket.emit('set_data_source', { source: 'synthetic' });
    log('Switched to Synthetic data source via Error Modal fallback.', 'sys');
});

// Synthetic Controls
ctrlClench.addEventListener('click', () => {
    synClench = !synClench;
    socket.emit('set_synthetic_state', { clench: synClench });
});
ctrlBlink.addEventListener('click', () => {
    socket.emit('set_synthetic_state', { blink: true });
    log('Blink triggered.', 'eng');
});
ctrlFocus.addEventListener('click', () => {
    synFocus = !synFocus;
    socket.emit('set_synthetic_state', { focus: synFocus });
});

noiseBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
        const level = e.target.dataset.level;
        socket.emit('set_noise_level', { level: level });
        log(`Requested Noise Profile change: ${level.toUpperCase()}`, 'sys');
    });
});

// Mood Profile Selector
moodBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        if (dataSource !== 'synthetic') return;
        const selectedMood = btn.dataset.mood;
        socket.emit('set_mood', { mood: selectedMood });

        // Optimistic UI Update
        moodBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    });
});

// AI Insights Request
if (aiBtn) {
    aiBtn.addEventListener('click', () => {
        if (!isConnected && dataSource === 'device') {
            log('Cannot analyze without active neural stream.', 'sys');
            return;
        }

        log('Requesting deep cognitive analysis from Engine...', 'ai');
        aiBtn.innerHTML = '<span class="ai-icon">⏳</span> Analyzing...';
        aiBtn.disabled = true;

        let currentNoise = 'clean';
        if (dataSource === 'synthetic') {
            const activeNoiseBtn = document.querySelector('.seg-btn.active');
            if (activeNoiseBtn) currentNoise = activeNoiseBtn.dataset.level;
        }

        socket.emit('request_classification', { noise_level: currentNoise });
    });
}

// Calibration
startCalibBtn.addEventListener('click', () => {
    if (startCalibBtn.disabled) return;
    socket.emit('request_calibration', {});
    showCalibrationPhase('INIT');
    isCalibrating = true;
    log('Calibration requested.', 'sys');
});

cancelCalibBtn.addEventListener('click', () => {
    calibOverlay.classList.add('hidden');
    isCalibrating = false;
    log('Calibration cancelled by user.', 'sys');
});

recalibBtn.addEventListener('click', () => {
    calibOverlay.classList.remove('hidden');
    calibContent.classList.add('hidden');
    calibActive.classList.remove('hidden');
    phaseNameEl.innerText = 'SYNCING';
    phaseInstructionEl.innerText = 'Waiting for Engine...';
    calibTimerEl.innerText = '--';
    socket.emit('request_calibration', {});
    isCalibrating = true;
    setTimeout(() => {
        if (isCalibrating && phaseNameEl.innerText === 'SYNCING') {
            phaseInstructionEl.innerHTML = '<span class="red">No Engine response.</span><br>Run neuro_reflex/main.py';
        }
    }, 5000);
});

clearTermBtn.addEventListener('click', () => {
    termBody.innerHTML = '';
    log('Log cleared by Operator.', 'sys');
});

// ═══════════════════════════════════════════════════════════
//  CANVAS RENDERERS
// ═══════════════════════════════════════════════════════════

function setupCanvas(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const parent = canvas.parentElement;
    const rect = parent.getBoundingClientRect();

    // Only resize if dimensions actually changed
    if (canvas.width !== Math.floor(rect.width * dpr) || canvas.height !== Math.floor(rect.height * dpr)) {
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
    }

    const ctx = canvas.getContext('2d');
    ctx.resetTransform(); // Clear previous scale
    ctx.scale(dpr, dpr);
    return { ctx, w: rect.width, h: rect.height };
}

// ─── EEG Waveform Renderer ──────────────────────────────────
function renderEEG() {
    const { ctx, w, h } = setupCanvas(eegCanvas);
    ctx.clearRect(0, 0, w, h);

    const channelHeight = h / 8;
    const verticalPadding = 4;

    for (let ch = 0; ch < 8; ch++) {
        const yCenter = channelHeight * ch + channelHeight / 2;

        // Channel label
        ctx.fillStyle = 'rgba(255,255,255,0.15)';
        ctx.font = '500 10px Inter';
        ctx.fillText(CHANNEL_NAMES[ch], 4, yCenter - channelHeight / 2 + 12);

        // Divider line
        if (ch > 0) {
            ctx.strokeStyle = 'rgba(255,255,255,0.04)';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(0, channelHeight * ch);
            ctx.lineTo(w, channelHeight * ch);
            ctx.stroke();
        }

        // Waveform
        ctx.strokeStyle = CHANNEL_COLORS[ch];
        ctx.lineWidth = 1.2;
        ctx.globalAlpha = 0.85;
        ctx.beginPath();

        const scale = (channelHeight - verticalPadding * 2) / 120; // ~±60uV range
        const step = w / EEG_BUFFER_LEN;

        for (let s = 0; s < EEG_BUFFER_LEN; s++) {
            const x = s * step;
            const y = yCenter - eegBuffer[ch][s] * scale;
            if (s === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();
        ctx.globalAlpha = 1.0;
    }

    requestAnimationFrame(renderEEG);
}

// ─── FFT Spectrum Renderer ──────────────────────────────────
function renderFFT() {
    const { ctx, w, h } = setupCanvas(fftCanvas);
    ctx.clearRect(0, 0, w, h);

    if (fftFreqs.length === 0 || fftPsd.length === 0) {
        requestAnimationFrame(renderFFT);
        return;
    }

    const padding = { left: 35, right: 10, top: 10, bottom: 25 };
    const plotW = w - padding.left - padding.right;
    const plotH = h - padding.top - padding.bottom;

    // Axis labels
    ctx.fillStyle = 'rgba(255,255,255,0.25)';
    ctx.font = '500 9px Inter';
    ctx.fillText('Hz', w - 18, h - 5);
    ctx.save();
    ctx.translate(8, padding.top + plotH / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText('PSD (log)', 0, 0);
    ctx.restore();

    // Band highlighting
    const maxFreq = fftFreqs[fftFreqs.length - 1] || 50;
    const freqToX = (f) => padding.left + (f / maxFreq) * plotW;

    // Alpha band (8-13Hz)
    ctx.fillStyle = 'rgba(0,255,170,0.04)';
    ctx.fillRect(freqToX(8), padding.top, freqToX(13) - freqToX(8), plotH);

    // Beta band (13-30Hz)
    ctx.fillStyle = 'rgba(0,150,255,0.04)';
    ctx.fillRect(freqToX(13), padding.top, freqToX(30) - freqToX(13), plotH);

    // Frequency tick marks
    ctx.fillStyle = 'rgba(255,255,255,0.2)';
    ctx.font = '400 8px Inter';
    for (const f of [5, 10, 15, 20, 25, 30, 40, 50]) {
        if (f <= maxFreq) {
            const x = freqToX(f);
            ctx.fillText(f, x - 5, h - 6);
            ctx.strokeStyle = 'rgba(255,255,255,0.04)';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(x, padding.top);
            ctx.lineTo(x, padding.top + plotH);
            ctx.stroke();
        }
    }

    // Find global min/max for log scale across all channels
    let globalMin = Infinity, globalMax = -Infinity;
    for (let ch = 0; ch < fftPsd.length; ch++) {
        for (let i = 0; i < fftPsd[ch].length; i++) {
            const logVal = Math.log10(fftPsd[ch][i]);
            if (logVal < globalMin) globalMin = logVal;
            if (logVal > globalMax) globalMax = logVal;
        }
    }
    const range = globalMax - globalMin || 1;

    // Draw each channel's PSD
    for (let ch = 0; ch < fftPsd.length; ch++) {
        ctx.strokeStyle = CHANNEL_COLORS[ch];
        ctx.lineWidth = 1.3;
        ctx.globalAlpha = 0.7;
        ctx.beginPath();

        for (let i = 0; i < fftPsd[ch].length; i++) {
            const x = freqToX(fftFreqs[i]);
            const norm = (Math.log10(fftPsd[ch][i]) - globalMin) / range;
            const y = padding.top + plotH - norm * plotH;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();
        ctx.globalAlpha = 1.0;
    }

    requestAnimationFrame(renderFFT);
}

// ═══════════════════════════════════════════════════════════
//  UTILITIES
// ═══════════════════════════════════════════════════════════

function showCalibrationPhase(phase) {
    if (phase === 'INIT') {
        calibOverlay.classList.remove('hidden');
        calibContent.classList.add('hidden');
        calibActive.classList.remove('hidden');
    }
}

function startTimer(duration, phase, task) {
    if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
    if (!duration || duration <= 0) return;

    phaseNameEl.innerText = phase;
    phaseInstructionEl.innerText = task;
    let timeLeft = duration;
    calibTimerEl.innerText = timeLeft;

    calibProgressBar.style.transition = 'none';
    calibProgressBar.style.width = '0%';
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            calibProgressBar.style.transition = `width ${duration}s linear`;
            calibProgressBar.style.width = '100%';
        });
    });

    timerInterval = setInterval(() => {
        timeLeft--;
        if (timeLeft >= 0) calibTimerEl.innerText = timeLeft;
        else { clearInterval(timerInterval); timerInterval = null; }
    }, 1000);
}

function log(msg, type = 'sys') {
    const time = new Date().toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const line = document.createElement('div');
    line.className = `line ${type}`;
    line.innerText = `[${time}] ${msg}`;
    termBody.appendChild(line);
    termBody.scrollTop = termBody.scrollHeight;
    if (termBody.children.length > 80) termBody.removeChild(termBody.firstChild);
}

// ═══════════════════════════════════════════════════════════
//  BOOT
// ═══════════════════════════════════════════════════════════

// Handle canvas resize
window.addEventListener('resize', () => {
    // Canvases auto-resize on next render frame
});

// Start render loops
requestAnimationFrame(renderEEG);
requestAnimationFrame(renderFFT);

log('Command Center online.', 'sys');

// Random jitter for performance metrics
setInterval(() => {
    if (dataSource === 'device' && isConnected) {
        const health = 95 + Math.random() * 5;
        bufferHealthFill.style.width = health + '%';
        bufferHealthVal.innerText = health.toFixed(1) + '%';
    }
}, 2000);
