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
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 50;
const RECONNECT_DELAY_MS = 2000;
let currentSource = 'video';

// ─── Gauge Definitions (must match config.py GAUGE_CHECKPOINTS) ─────────
const GAUGE_NAMES = {
    1: 'Distance Gauge',
    2: 'Pin Gauge',
    3: 'Dia Gauge',
    4: 'M8 Thread',
    5: 'M6 Thread',
    6: 'Hydraulic Head',
    7: '13mm Gauge',
};

// ─── Initialize ─────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initClock();
    initGaugeList();
    connectWebSocket();

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

    if (data.source) {
        currentSource = data.source;
        updateSourceButtons(data.source);
        updateCameraModeLabel(data.source);
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
        item.setAttribute('data-status', 'PENDING');

        item.innerHTML = `
            <span class="gauge-num">${id}</span>
            <span class="gauge-name">${name}</span>
            <span class="gauge-status-badge">
                <span class="gauge-status-icon">◯</span>
                <span class="gauge-status-text">Pending</span>
            </span>
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
        item.setAttribute('data-status', status);

        const badge = item.querySelector('.gauge-status-badge');
        const iconEl = item.querySelector('.gauge-status-icon');
        const textEl = item.querySelector('.gauge-status-text');

        if (status === 'OK') {
            completed++;
            iconEl.textContent = '✓';
            textEl.textContent = 'Checked';
        } else if (status === 'NG') {
            iconEl.textContent = '✗';
            textEl.textContent = 'NG';
        } else if (status === 'WAITING') {
            iconEl.textContent = '◔';
            textEl.textContent = 'Waiting';
        } else if (status === 'NO_GAUGE') {
            iconEl.textContent = '◔';
            textEl.textContent = 'No Gauge';
        } else if (status === 'NO_AREA') {
            iconEl.textContent = '◔';
            textEl.textContent = 'No Area';
        } else if (status === 'UNCERTAIN') {
            iconEl.textContent = '◔';
            textEl.textContent = 'Checking...';
        } else {
            iconEl.textContent = '◯';
            textEl.textContent = 'Pending';
        }
    }

    // Update counter
    const counterEl = document.getElementById('gauge-counter');
    if (counterEl) {
        counterEl.textContent = `(${completed} / ${total})`;
    }
}

// ─── Inspection State Banner ─────────────────────────────────────────────────
function updateInspectionState(state) {
    const stateEl = document.getElementById('inspection-state-label');
    if (!stateEl) return;
    const labels = {
        IDLE:       '\u23f3  Waiting for Part',
        INSPECTING: '\u25cf  Inspection in Progress',
        COMPLETE:   '\u2713  Complete \u2014 Remove Part',
    };
    const colors = { IDLE: '#7f8c8d', INSPECTING: '#f39c12', COMPLETE: '#2ecc71' };
    stateEl.textContent = labels[state] || (state || '');
    stateEl.style.color = colors[state] || '#ccc';
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
        statusEl.style.color = '#7f8c8d';
        iconEl.innerHTML = `
            <svg class="result-svg" viewBox="0 0 60 60">
                <circle cx="30" cy="30" r="26" fill="none" stroke="#555" stroke-width="3" stroke-dasharray="5,5"/>
                <text x="30" y="37" text-anchor="middle" fill="#555" font-size="20" font-family="Inter">⏳</text>
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
                <circle cx="30" cy="30" r="26" fill="rgba(46,204,113,0.15)" stroke="#2ecc71" stroke-width="3"/>
                <path d="M18 30 L26 38 L42 22" fill="none" stroke="#2ecc71" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>`;
    } else if (status === 'NG') {
        card.classList.add('status-ng');
        statusEl.style.color = '';
        statusEl.textContent = 'FAIL';
        iconEl.innerHTML = `
            <svg class="result-svg" viewBox="0 0 60 60">
                <circle cx="30" cy="30" r="26" fill="rgba(231,76,60,0.15)" stroke="#e74c3c" stroke-width="3"/>
                <path d="M20 20 L40 40 M40 20 L20 40" fill="none" stroke="#e74c3c" stroke-width="3.5" stroke-linecap="round"/>
            </svg>`;
    } else {
        card.classList.add('status-progress');
        statusEl.style.color = '';
        statusEl.textContent = 'Under Progress';
        iconEl.innerHTML = `
            <svg class="result-svg" viewBox="0 0 60 60">
                <circle cx="30" cy="30" r="26" fill="rgba(243,156,18,0.15)" stroke="#f39c12" stroke-width="3" stroke-dasharray="8,4">
                    <animateTransform attributeName="transform" type="rotate" from="0 30 30" to="360 30 30" dur="8s" repeatCount="indefinite"/>
                </circle>
                <text x="30" y="35" text-anchor="middle" fill="#f39c12" font-size="16" font-weight="bold" font-family="Inter">⟳</text>
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
            ? '<span class="status-dot online"></span><span>Active</span>'
            : '<span class="status-dot offline"></span><span>Offline</span>';
        detEl.style.color = detectorAvailable ? 'var(--status-ok)' : 'var(--status-ng)';
    }

    if (camEl) {
        camEl.innerHTML = cameraConnected
            ? '<span class="status-dot online"></span><span>Active</span>'
            : '<span class="status-dot offline"></span><span>Offline</span>';
        camEl.style.color = cameraConnected ? 'var(--status-ok)' : 'var(--status-ng)';
    }
}

function updateSystemStatus(connected) {
    const indicator = document.getElementById('system-status-indicator');
    if (!indicator) return;

    if (connected) {
        indicator.innerHTML = '<span class="status-dot online"></span><span class="status-label">System Online</span>';
        indicator.style.borderColor = 'rgba(46, 204, 113, 0.3)';
    } else {
        indicator.innerHTML = '<span class="status-dot offline"></span><span class="status-label" style="color:var(--status-ng)">Disconnected</span>';
        indicator.style.borderColor = 'rgba(231, 76, 60, 0.3)';
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
                <td>${index + 1}</td>
                <td>${log.time}</td>
                <td>${log.part_id}</td>
                <td>
                    <span class="log-result ${resultClass}">
                        <span class="log-result-icon">${resultIcon}</span>
                        ${log.result}
                    </span>
                </td>
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

            // Refresh video feed
            const videoEl = document.getElementById('video-feed');
            if (videoEl) {
                videoEl.src = '/video?' + Date.now();
            }
        }
    } catch (e) {
        console.error('Failed to switch source:', e);
    }
}

function updateSourceButtons(mode) {
    document.querySelectorAll('.btn-source').forEach(btn => {
        btn.classList.remove('active');
    });

    const activeBtn = document.getElementById(`btn-${mode}`);
    if (activeBtn) {
        activeBtn.classList.add('active');
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
