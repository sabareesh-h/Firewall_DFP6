/**
 * SOP Compliance System — Frontend Client
 *
 * Handles:
 * - WebSocket connection for real-time status updates
 * - Gauge checkpoint rendering
 * - Production counters
 * - Live clock
 * - Source switching (live / video / demo)
 * - Reset functionality
 * - Recent logs table
 */

// ─── State ──────────────────────────────────────────────────────────────────
let ws = null;
let wsVideo = null;
let reconnectAttempts = 0;
let videoReconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 50;
const RECONNECT_DELAY_MS = 2000;
let currentSource = 'video';

// ─── Gauge Definitions (must match config.py GAUGE_CHECKPOINTS) ─────────
const GAUGE_NAMES = {
    1: 'Distance Gauge',
    2: 'Pin Gauge',
    3: 'Dia Gauge',
    4: 'M6 Thread',
    5: 'M8 Thread',
    6: '11mm Gauge',
    7: '13mm Gauge',
};

const GAUGE_IMAGES = {
    1: 'Distance.png',
    2: 'Pin Gauge.png',
    3: 'Dia Gauge.png',
    4: 'M6 Gauge.png',
    5: 'M8 Gauge.png',
    6: '11mm Gauge.png',
    7: '13mm Gauge.png',
};

// ─── Initialize ─────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initClock();
    initGaugeList();
    connectWebSocket();
    connectVideoWebSocket();

    // Fallback: poll status if WebSocket fails
    setInterval(pollStatus, 3000);
});

// ─── Clock ──────────────────────────────────────────────────────────────────
function initClock() {
    updateClock();
    setInterval(updateClock, 1000);
}

function updateClock() {
    const now = new Date();
    const dateStr = now.toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
    });
    const timeStr = now.toLocaleTimeString('en-IN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
    });

    const dateEl = document.getElementById('header-date');
    const timeEl = document.getElementById('header-time');
    if (dateEl) dateEl.textContent = dateStr;
    if (timeEl) timeEl.textContent = timeStr;
}

// ─── WebSocket ──────────────────────────────────────────────────────────────
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    try {
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log('WebSocket connected');
            reconnectAttempts = 0;
            updateSystemStatus(true);
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleStatusUpdate(data);
            } catch (e) {
                console.error('Failed to parse WebSocket message:', e);
            }
        };

        ws.onclose = () => {
            console.log('WebSocket disconnected');
            updateSystemStatus(false);
            scheduleReconnect();
        };

        ws.onerror = (err) => {
            console.error('WebSocket error:', err);
            updateSystemStatus(false);
        };

        // Keep-alive ping
        setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send('ping');
            }
        }, 15000);

    } catch (e) {
        console.error('WebSocket connection failed:', e);
        scheduleReconnect();
    }
}

// ─── Video WebSocket ────────────────────────────────────────────────────────
let _videoCanvas = null;
let _videoCtx = null;
let _videoFpsCount = 0;
let _videoFpsTime = performance.now();
let _videoFps = 0;

function connectVideoWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/video`;

    try {
        wsVideo = new WebSocket(wsUrl);
        wsVideo.binaryType = 'arraybuffer';

        wsVideo.onopen = () => {
            console.log('Video WebSocket connected');
            videoReconnectAttempts = 0;
        };

        wsVideo.onmessage = (event) => {
            if (!(event.data instanceof ArrayBuffer)) return;

            // Lazily grab the canvas and context
            if (!_videoCanvas) {
                _videoCanvas = document.getElementById('video-canvas');
                if (_videoCanvas) _videoCtx = _videoCanvas.getContext('2d');
            }
            if (!_videoCtx) return;

            // Convert binary JPEG to an image and draw on canvas
            const blob = new Blob([event.data], { type: 'image/jpeg' });
            const url = URL.createObjectURL(blob);
            const img = new Image();
            img.onload = () => {
                // Auto-resize canvas to match frame aspect ratio
                if (_videoCanvas.width !== img.width || _videoCanvas.height !== img.height) {
                    _videoCanvas.width = img.width;
                    _videoCanvas.height = img.height;
                }
                _videoCtx.drawImage(img, 0, 0);
                URL.revokeObjectURL(url);

                // Track received FPS
                _videoFpsCount++;
                const now = performance.now();
                if (now - _videoFpsTime >= 2000) {
                    _videoFps = Math.round(_videoFpsCount / ((now - _videoFpsTime) / 1000));
                    _videoFpsCount = 0;
                    _videoFpsTime = now;
                    console.log(`Video WS: ${_videoFps} FPS`);
                }
            };
            img.src = url;
        };

        wsVideo.onclose = () => {
            console.log('Video WebSocket disconnected');
            scheduleVideoReconnect();
        };

        wsVideo.onerror = (err) => {
            console.error('Video WebSocket error:', err);
        };

        // Keep-alive ping every 15s
        setInterval(() => {
            if (wsVideo && wsVideo.readyState === WebSocket.OPEN) {
                wsVideo.send('ping');
            }
        }, 15000);

    } catch (e) {
        console.error('Video WebSocket connection failed:', e);
        scheduleVideoReconnect();
    }
}

function scheduleVideoReconnect() {
    if (videoReconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        videoReconnectAttempts++;
        setTimeout(connectVideoWebSocket, RECONNECT_DELAY_MS);
    }
}

function scheduleReconnect() {
    if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttempts++;
        setTimeout(connectWebSocket, RECONNECT_DELAY_MS);
    }
}

// ─── Fallback Polling ───────────────────────────────────────────────────────
async function pollStatus() {
    // Only poll if WebSocket is not connected
    if (ws && ws.readyState === WebSocket.OPEN) return;

    try {
        const response = await fetch('/status');
        if (response.ok) {
            const data = await response.json();
            handleStatusUpdate(data);
        }
    } catch (e) {
        // Silently fail — will retry
    }
}

// ─── Status Update Handler ──────────────────────────────────────────────────
function handleStatusUpdate(data) {
    updateGauges(data.gauges || {});
    updateOverallResult(data.overall_status, data.inspection_state, data.completed, data.total);
    updateInspectionState(data.inspection_state);
    updateProduction(data.production || {});
    updateConnections(data.detector_available, data.camera_connected);
    updateLogs(data.recent_logs || []);
    updateHeaderStatuses(data.detector_available, data.camera_connected);
    updateSafetyWarning(data.glove_warning);

    const partNoEl = document.getElementById('scanned-part-no');
    if (partNoEl) {
        if (data.scanned_part_no) {
            partNoEl.textContent = data.scanned_part_no;
        } else {
            partNoEl.textContent = '--';
        }
    }

    if (data.source) {
        currentSource = data.source;
        updateSourceButtons(data.source);
        updateCameraModeLabel(data.source);
    }
    
    // Render the Smart Overlays
    if (data.raw_detections) {
        updateSmartOverlays(data);
    }
}

// ─── Smart Focus Overlays ───────────────────────────────────────────────────
let previousBoxIds = new Set();
function updateSmartOverlays(data) {
    const container = document.getElementById('smart-overlay-container');
    const canvas = document.getElementById('video-canvas');
    if (!container || !canvas || !data.raw_detections) return;

    // We calculate scaling factor based on original frame size vs rendered canvas client size
    const cw = canvas.clientWidth;
    const ch = canvas.clientHeight;
    if (cw === 0 || ch === 0) return; // Not visible yet

    const scaleX = cw / (data.frame_width || 1280);
    const scaleY = ch / (data.frame_height || 720);

    const currentBoxIds = new Set();
    const classCounts = {};

    data.raw_detections.forEach((det) => {
        // Stable ID generation to prevent CSS transition flickering when array index changes
        const safeClassName = det.class_name.replace(/\s+/g, '-');
        classCounts[safeClassName] = (classCounts[safeClassName] || 0) + 1;
        const id = `det-${safeClassName}-${classCounts[safeClassName]}`;
        
        currentBoxIds.add(id);

        let box = document.getElementById(id);
        if (!box) {
            box = document.createElement('div');
            box.id = id;
            box.className = 'smart-box';
            
            const label = document.createElement('div');
            label.className = 'smart-label';
            box.appendChild(label);
            
            container.appendChild(box);
        }

        // Positioning
        const [x1, y1, x2, y2] = det.bbox;
        const left = x1 * scaleX;
        const top = y1 * scaleY;
        const width = (x2 - x1) * scaleX;
        const height = (y2 - y1) * scaleY;

        box.style.left = `${left}px`;
        box.style.top = `${top}px`;
        box.style.width = `${width}px`;
        box.style.height = `${height}px`;

        // Content
        const labelDiv = box.querySelector('.smart-label');
        let labelText = det.class_name;
        if (data.show_confidence_score) {
            labelText += ` <span>${det.confidence.toFixed(2)}</span>`;
        }
        labelDiv.innerHTML = labelText;

        // Styling State
        let isGauge = false;
        let gaugeStatus = null;
        let dwellProgress = 0;

        // Match YOLO class name (e.g., "Pin") with gauge name (e.g., "Pin Gauge")
        if (data.gauges) {
            for (const key in data.gauges) {
                if (data.gauges[key].name.startsWith(det.class_name)) {
                    isGauge = true;
                    gaugeStatus = data.gauges[key].status;
                    dwellProgress = data.gauges[key].dwell_progress;
                    break;
                }
            }
        }
        
        // Parts usually aren't gauges
        if (det.class_name === 'Part' || det.class_name === 'Hand' || !isGauge) {
            box.className = 'smart-box idle-part';
            if (det.class_name === 'Hand') {
                box.style.borderColor = 'rgba(220, 38, 38, 0.6)';
                labelDiv.style.background = 'rgba(220, 38, 38, 0.9)';
            }
        } else {
            // It's a Gauge
            if (gaugeStatus === 'OK' && dwellProgress >= 1.0) {
                box.className = 'smart-box success';
                labelDiv.innerHTML = `✅ ${labelText}`;
            } else if (dwellProgress > 0 || gaugeStatus === 'UNCERTAIN') {
                box.className = 'smart-box active';
                labelDiv.innerHTML = `🎯 ${labelText}`;
            } else {
                box.className = 'smart-box idle-gauge';
            }
        }
    });

    // Remove old boxes that disappeared
    previousBoxIds.forEach(id => {
        if (!currentBoxIds.has(id)) {
            const el = document.getElementById(id);
            if (el) el.remove();
        }
    });
    previousBoxIds = currentBoxIds;
}

function toggleFocusMode() {
    const container = document.getElementById('smart-overlay-container');
    const toggle = document.getElementById('focus-mode-toggle');
    if (container && toggle) {
        if (toggle.checked) {
            container.classList.add('focus-mode-on');
        } else {
            container.classList.remove('focus-mode-on');
        }
    }
}


// ─── Gauge List ─────────────────────────────────────────────────────────────
function initGaugeList() {
    const container = document.getElementById('gauge-list');
    if (!container) return;

    container.innerHTML = '';

    for (const [id, name] of Object.entries(GAUGE_NAMES)) {
        const item = document.createElement('div');
        item.className = 'gauge-item';
        item.id = `gauge-item-${id}`;
        item.setAttribute('data-status', 'NOT_CHECKED');

        const imageName = GAUGE_IMAGES[id];
        const imageHtml = `<img src="/reference_images/${imageName}" alt="${name}" style="max-height: 24px; max-width: 36px; object-fit: contain;" />`;

        item.innerHTML = `
            <span class="gauge-num" style="width: 24px; height: 24px; font-size: 12px; flex-shrink: 0;">${id}</span>
            <div style="width: 50px; display: flex; justify-content: center; align-items: center; flex-shrink: 0; margin-left: 8px;">
                ${imageHtml}
            </div>
            <div class="gauge-name" style="flex: 1; font-size: 14px; font-weight: 700; text-align: right;">${name}</div>
        `;

        container.appendChild(item);
    }
}

function updateGauges(gauges) {
    let completed = 0;
    const total = Object.keys(GAUGE_NAMES).length;

    for (const [key, gauge] of Object.entries(gauges)) {
        const id = gauge.id;
        const item = document.getElementById(`gauge-item-${id}`);
        if (!item) continue;

        const status = gauge.status;
        const dwell = gauge.dwell_progress || 0;  // 0.0 to 1.0

        let displayStatus = 'NOT_CHECKED';
        if (status === 'OK') {
            displayStatus = 'OK';
            completed++;
        } else if (dwell > 0 && status === 'UNCERTAIN') {
            displayStatus = 'UNCERTAIN';
        }

        item.setAttribute('data-status', displayStatus);
    }

    // Update counter
    const counterEl = document.getElementById('gauge-counter');
    if (counterEl) {
        counterEl.textContent = `${completed} / ${total} Completed`;
    }

    // Update progress bar
    const progressFill = document.getElementById('gauge-progress-fill');
    if (progressFill) {
        const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
        progressFill.style.width = pct + '%';
        progressFill.style.background = completed === total
            ? 'var(--ok)'
            : 'linear-gradient(90deg, var(--accent), var(--ok))';
    }
}


// ─── Inspection State Banner ─────────────────────────────────────────────────
function updateInspectionState(state) {
    const stateEl = document.getElementById('inspection-state-label');
    if (!stateEl) return;
    const labels = {
        IDLE: '\u23f3  Waiting for Part',
        INSPECTING: '\u25cf  Inspection in Progress',
        COMPLETE: '\u2713  Complete \u2014 Remove Part',
    };
    const colors = { IDLE: '#94a3b8', INSPECTING: '#d97706', COMPLETE: '#16a34a' };
    stateEl.textContent = labels[state] || (state || '');
    stateEl.style.color = colors[state] || '#94a3b8';
}

// ─── Overall Result ──────────────────────────────────────────────────────────
function updateOverallResult(status, inspectionState, completed, total) {

    const card = document.getElementById('result-card');
    const statusEl = document.getElementById('result-status');
    const detailEl = document.getElementById('result-detail');
    const iconEl = document.getElementById('result-icon');

    if (!card || !statusEl) return;

    card.classList.remove('status-ok', 'status-ng', 'status-progress');

    if (inspectionState === 'IDLE' || status === 'WAITING') {
        statusEl.textContent = 'Waiting for Part';
        statusEl.style.color = '#94a3b8';
        iconEl.innerHTML = `
            <svg class="result-svg" viewBox="0 0 60 60">
                <circle cx="30" cy="30" r="26" fill="none" stroke="#cbd5e1" stroke-width="2.5" stroke-dasharray="5,5"/>
                <text x="30" y="37" text-anchor="middle" fill="#94a3b8" font-size="20" font-family="Inter">⏳</text>
            </svg>`;
        if (detailEl) detailEl.textContent = 'Place part on table to begin';
        return;
    }

    if (inspectionState === 'COMPLETE' || status === 'OK') {
        card.classList.add('status-ok');
        statusEl.style.color = '';
        statusEl.textContent = 'PASS';
        iconEl.innerHTML = `
            <svg class="result-svg" viewBox="0 0 60 60">
                <circle cx="30" cy="30" r="26" fill="rgba(22,163,74,0.10)" stroke="#16a34a" stroke-width="2.5"/>
                <path d="M18 30 L26 38 L42 22" fill="none" stroke="#16a34a" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>`;
    } else if (status === 'NG') {
        card.classList.add('status-ng');
        statusEl.style.color = '';
        statusEl.textContent = 'FAIL';
        iconEl.innerHTML = `
            <svg class="result-svg" viewBox="0 0 60 60">
                <circle cx="30" cy="30" r="26" fill="rgba(220,38,38,0.08)" stroke="#dc2626" stroke-width="2.5"/>
                <path d="M20 20 L40 40 M40 20 L20 40" fill="none" stroke="#dc2626" stroke-width="3.5" stroke-linecap="round"/>
            </svg>`;
    } else {
        card.classList.add('status-progress');
        statusEl.style.color = '';
        statusEl.textContent = 'Under Progress';
        iconEl.innerHTML = `
            <svg class="result-svg" viewBox="0 0 60 60">
                <circle cx="30" cy="30" r="26" fill="rgba(37,99,235,0.06)" stroke="#2563eb" stroke-width="2.5" stroke-dasharray="8,4">
                    <animateTransform attributeName="transform" type="rotate" from="0 30 30" to="360 30 30" dur="8s" repeatCount="indefinite"/>
                </circle>
                <text x="30" y="35" text-anchor="middle" fill="#2563eb" font-size="16" font-weight="bold" font-family="Inter">⟳</text>
            </svg>`;
    }

    if (detailEl) {
        detailEl.textContent = `${completed || 0} / ${total || 7} gauges completed`;
    }
}

// ─── Production Counters ────────────────────────────────────────────────────
function updateProduction(production) {
    const totalEl = document.getElementById('total-count');
    const passEl = document.getElementById('pass-count');
    const failEl = document.getElementById('fail-count');

    if (totalEl) totalEl.textContent = production.total_count || 0;
    if (passEl) passEl.textContent = production.pass_count || 0;
    if (failEl) failEl.textContent = production.fail_count || 0;
}

// ─── Connection Status ──────────────────────────────────────────────────────
function updateConnections(detectorAvailable, cameraConnected) {
    const detEl = document.getElementById('conn-detector');
    const camEl = document.getElementById('conn-camera');

    if (detEl) {
        detEl.innerHTML = detectorAvailable
            ? '<span class="status-dot online"></span><span>Connected</span>'
            : '<span class="status-dot offline"></span><span>Offline</span>';
        detEl.style.color = detectorAvailable ? 'var(--status-ok)' : 'var(--status-ng)';
    }

    if (camEl) {
        camEl.innerHTML = cameraConnected
            ? '<span class="status-dot online"></span><span>Connected</span>'
            : '<span class="status-dot offline"></span><span>Offline</span>';
        camEl.style.color = cameraConnected ? 'var(--status-ok)' : 'var(--status-ng)';
    }
}

function updateHeaderStatuses(detectorAvailable, cameraConnected) {
    const camStatusEl = document.getElementById('header-camera-status');
    const yoloStatusEl = document.getElementById('header-yolo-status');

    if (camStatusEl) {
        camStatusEl.textContent = cameraConnected ? 'Online' : 'Offline';
        camStatusEl.style.color = cameraConnected ? 'var(--status-ok)' : 'var(--status-ng)';
    }
    if (yoloStatusEl) {
        yoloStatusEl.textContent = detectorAvailable ? 'Online' : 'Offline';
        yoloStatusEl.style.color = detectorAvailable ? 'var(--status-ok)' : 'var(--status-ng)';
    }
}

function updateSystemStatus(connected) {
    const indicator = document.getElementById('system-status-indicator');
    if (!indicator) return;

    if (connected) {
        indicator.innerHTML = '<span class="status-dot online"></span><span class="status-label">System Online</span>';
        indicator.style.borderColor = 'rgba(22, 163, 74, 0.20)';
    } else {
        indicator.innerHTML = '<span class="status-dot offline"></span><span class="status-label" style="color:var(--ng)">Disconnected</span>';
        indicator.style.borderColor = 'rgba(220, 38, 38, 0.20)';
    }
}

function updateSafetyWarning(isWarningActive) {
    const overlay = document.getElementById('safety-warning-overlay');
    if (!overlay) return;

    if (isWarningActive) {
        overlay.style.display = 'flex';
    } else {
        overlay.style.display = 'none';
    }
}

// ─── Recent Logs ────────────────────────────────────────────────────────────
function updateLogs(logs) {
    const tbody = document.getElementById('logs-tbody');
    if (!tbody) return;

    if (!logs || logs.length === 0) {
        tbody.innerHTML = '<tr class="log-empty"><td colspan="4">No inspection logs yet</td></tr>';
        return;
    }

    // Show most recent first
    const reversed = [...logs].reverse();

    tbody.innerHTML = reversed.map((log, index) => {
        const isOk = log.result === 'OK';
        const resultClass = isOk ? 'ok' : 'ng';
        const resultIcon = isOk ? '✓' : '✗';

        return `
            <tr>
                <td>${log.time}</td>
                <td>${log.part_id}</td>
                <td>
                    <span class="log-result ${resultClass}">
                        <span class="log-result-icon">${resultIcon}</span>
                        ${log.result}
                    </span>
                </td>
                <td>${log.cycle_time || '--'}</td>
            </tr>
        `;
    }).join('');
}

// ─── Source Switching ───────────────────────────────────────────────────────
async function switchSource(mode) {
    try {
        const body = { mode: mode };
        if (mode === 'video') {
            // Uses default video path configured in backend
            body.source = null;
        }

        const response = await fetch('/source', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        if (response.ok) {
            currentSource = mode;
            updateSourceButtons(mode);
            updateCameraModeLabel(mode);
            // Video feed auto-updates via WebSocket — no refresh needed
        }
    } catch (e) {
        console.error('Failed to switch source:', e);
    }
}

function updateSourceButtons(mode) {
    const select = document.getElementById('header-source-select');
    if (select) {
        select.value = mode;
    }
}

function updateCameraModeLabel(mode) {
    const label = document.getElementById('camera-mode-label');
    if (!label) return;

    const labels = {
        live: '(LIVE CAMERA)',
        video: '(PRE-RECORDED VIDEO)',
        demo: '(DEMO MODE)',
    };

    label.textContent = labels[mode] || '';
}

// ─── Reset ──────────────────────────────────────────────────────────────────
async function resetInspection() {
    try {
        const response = await fetch('/reset', { method: 'POST' });
        if (response.ok) {
            const data = await response.json();
            handleStatusUpdate(data);
        }
    } catch (e) {
        console.error('Failed to reset inspection:', e);
    }
}

async function resetCounter() {
    try {
        await fetch('/reset_counter', { method: 'POST' });
        // Counters will update via next WebSocket message
        document.getElementById('total-count').textContent = '0';
        document.getElementById('pass-count').textContent = '0';
        document.getElementById('fail-count').textContent = '0';
    } catch (e) {
        console.error('Failed to reset counter:', e);
    }
}

// ─── Settings ───────────────────────────────────────────────────────────────
async function toggleConfidence() {
    const toggle = document.getElementById('conf-toggle');
    if (!toggle) return;
    try {
        await fetch('/settings/confidence', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ show: toggle.checked })
        });
    } catch (e) {
        console.error('Failed to toggle confidence:', e);
    }
}

async function togglePacing() {
    const toggle = document.getElementById('pacing-toggle');
    if (!toggle) return;
    try {
        await fetch('/settings/pacing', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enable: toggle.checked })
        });
    } catch (e) {
        console.error('Failed to toggle pacing:', e);
    }
}

// ─── Barcode Scanner ────────────────────────────────────────────────────────
let barcodeBuffer = '';
let lastKeyTime = 0;

document.addEventListener('keydown', (e) => {
    // Ignore if user is manually typing in an input field
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    const currentTime = new Date().getTime();

    // Most hardware scanners act as a keyboard and emit keys very rapidly
    if (currentTime - lastKeyTime > 100) {
        barcodeBuffer = ''; // Reset buffer if more than 100ms passed between keystrokes
    }

    if (e.key === 'Enter') {
        if (barcodeBuffer.length > 0) {
            handleBarcodeScanned(barcodeBuffer);
            barcodeBuffer = '';
        }
    } else if (e.key.length === 1) { // Normal printable character
        barcodeBuffer += e.key;
    }

    lastKeyTime = currentTime;
});

function handleBarcodeScanned(code) {
    console.log("Scanned part number:", code);
    const partNoEl = document.getElementById('scanned-part-no');
    if (partNoEl) {
        partNoEl.textContent = code;
        // Send to backend
        fetch('/set_part_no', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ part_no: code })
        }).catch(err => console.error("Failed to set part no:", err));
    }
}

// ─── Admin Panel ────────────────────────────────────────────────────────────

function openAdminModal() {
    document.getElementById('admin-modal').style.display = 'flex';
    document.getElementById('admin-login-view').style.display = 'block';
    document.getElementById('admin-settings-view').style.display = 'none';
    document.getElementById('admin-title').textContent = 'Admin Login';
    document.getElementById('admin-pin').value = '';
    document.getElementById('admin-pin').focus();
}

function closeAdminModal() {
    document.getElementById('admin-modal').style.display = 'none';
}

function verifyAdminPin() {
    const pin = document.getElementById('admin-pin').value;
    // In a real app, verify via backend. Here, hardcoded to 1234.
    if (pin === '1234') {
        document.getElementById('admin-login-view').style.display = 'none';
        document.getElementById('admin-settings-view').style.display = 'block';
        document.getElementById('admin-title').textContent = 'Dynamic Settings';
        fetchAdminSettings();
    } else {
        alert('Incorrect PIN');
    }
}

async function fetchAdminSettings() {
    try {
        const response = await fetch('/settings');
        if (response.ok) {
            const data = await response.json();
            document.getElementById('set-conf').value = data.confidence_threshold;
            document.getElementById('set-overlap').value = data.overlap_threshold;
            document.getElementById('set-near').value = data.near_distance_threshold;
            document.getElementById('set-dwell').value = data.ok_hold_seconds;
            if (data.visual_deadzone) {
                document.getElementById('set-deadzone').value = data.visual_deadzone.join(', ');
            } else {
                document.getElementById('set-deadzone').value = '';
            }
            
            // Populate individual gauges
            const container = document.getElementById('gauge-settings-container');
            container.innerHTML = ''; // clear
            
            if (data.gauge_configs) {
                data.gauge_configs.forEach(g => {
                    const html = `
                        <div class="admin-gauge-card" style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; margin-bottom: 12px;" data-id="${g.id}">
                            <div style="font-weight: 700; color: #334155; margin-bottom: 8px; font-size: 13px;">#${g.id} — ${g.name}</div>
                            
                            <div class="admin-field" style="margin-bottom: 8px;">
                                <label style="font-size: 11px;">Method</label>
                                <select class="g-method" style="width: 100%; padding: 6px; border: 1px solid #cbd5e1; border-radius: 4px; font-size: 12px;">
                                    <option value="near" ${g.method === 'near' ? 'selected' : ''}>Near Distance</option>
                                    <option value="intersects" ${g.method === 'intersects' ? 'selected' : ''}>Intersects / Overlaps Area</option>
                                    <option value="inside" ${g.method === 'inside' ? 'selected' : ''}>Center Inside Area</option>
                                    <option value="fully_inside" ${g.method === 'fully_inside' ? 'selected' : ''}>Fully Inside Area</option>
                                </select>
                            </div>
                            
                            <div style="display: flex; gap: 10px;">
                                <div class="admin-field" style="flex: 1; margin-bottom: 0;">
                                    <label style="font-size: 11px;">Near Thresh (px)</label>
                                    <input type="number" class="g-near" value="${g.near_distance_threshold}" step="10" style="padding: 6px; font-size: 12px;">
                                </div>
                                <div class="admin-field" style="flex: 1; margin-bottom: 0;">
                                    <label style="font-size: 11px;">Overlap Thresh</label>
                                    <input type="number" class="g-overlap" value="${g.overlap_threshold}" step="0.05" style="padding: 6px; font-size: 12px;">
                                </div>
                            </div>
                        </div>
                    `;
                    container.insertAdjacentHTML('beforeend', html);
                });
            }
        }
    } catch (e) {
        console.error('Failed to fetch settings:', e);
    }
}

async function saveAdminSettings() {
    const conf = parseFloat(document.getElementById('set-conf').value);
    const overlap = parseFloat(document.getElementById('set-overlap').value);
    const near = parseInt(document.getElementById('set-near').value);
    const dwell = parseFloat(document.getElementById('set-dwell').value);
    
    let deadzone = null;
    const deadzoneStr = document.getElementById('set-deadzone').value.trim();
    if (deadzoneStr) {
        const parts = deadzoneStr.split(',').map(s => parseInt(s.trim()));
        if (parts.length === 4 && parts.every(p => !isNaN(p))) {
            deadzone = parts;
        } else {
            alert('Visual Deadzone must be 4 numbers separated by commas (x1, y1, x2, y2)');
            return;
        }
    }
    
    // Collect gauge configs
    const gauge_configs = [];
    document.querySelectorAll('.admin-gauge-card').forEach(card => {
        gauge_configs.push({
            id: parseInt(card.getAttribute('data-id')),
            method: card.querySelector('.g-method').value,
            near_distance_threshold: parseInt(card.querySelector('.g-near').value),
            overlap_threshold: parseFloat(card.querySelector('.g-overlap').value)
        });
    });

    try {
        const response = await fetch('/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                confidence_threshold: conf,
                overlap_threshold: overlap,
                near_distance_threshold: near,
                ok_hold_seconds: dwell,
                gauge_configs: gauge_configs,
                visual_deadzone: deadzone
            })
        });

        if (response.ok) {
            alert('Settings updated successfully!');
            closeAdminModal();
        } else {
            alert('Failed to update settings');
        }
    } catch (e) {
        console.error('Failed to save settings:', e);
    }
}
