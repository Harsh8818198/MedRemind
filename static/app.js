/* ==========================================================================
   MedRemind Caregiver Portal client JS Controller
   Logic: REST API Client, Metrics, SPA Tab Switcher, & Stateful Call Simulator
   ========================================================================== */

document.addEventListener("DOMContentLoaded", () => {
    // Initialize Dashboard UI Elements
    initModalControls();
    initTabSwitcher();
    initEscalationModal();
    initMockupBindings();
    loadDashboardData();
    
    // Quick Test Call listener
    document.getElementById("btn-quick-test").addEventListener("click", () => {
        triggerSimulatedCall("mock-test");
    });

    // Auto-refresh feed metrics every 10 seconds for live updates from background scheduler!
    setInterval(loadDashboardData, 10000);
});

// --------------------------------------------------------------------------
// 1. Core State & Data Fetching
// --------------------------------------------------------------------------

// Local memory cache
let cachedReminders = [];
let cachedLogs = [];
let lastSeenLogId = 0;

function loadDashboardData() {
    loadReminders();
    loadLogs();
    loadRiskScores();
    loadInsightsData();
}

async function loadReminders() {
    const tbody = document.getElementById("reminders-tbody");
    const boardTbody = document.getElementById("schedule-board-tbody");
    
    try {
        const response = await fetch("/api/reminders");
        const reminders = await response.json();
        cachedReminders = reminders;
        
        // Update metric counts
        const remindersCountEl = document.getElementById("metric-reminders");
        if (remindersCountEl) {
            remindersCountEl.innerText = reminders.length;
        }
        
        // 1. Render Dashboard Table Preview (if element exists)
        if (tbody) {
            if (reminders.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="6" class="table-empty">
                            No active reminders scheduled. Use '+ Add Medication' to create one!
                        </td>
                    </tr>`;
            } else {
                tbody.innerHTML = "";
                reminders.forEach(r => {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td><strong>${escapeHtml(r.patient)}</strong></td>
                        <td><span class="badge">${escapeHtml(r.medication)}</span></td>
                        <td>${escapeHtml(r.dosage)}</td>
                        <td><strong style="color:var(--clr-blue);">${r.time}</strong></td>
                        <td><span class="text-secondary">${r.next_run}</span></td>
                        <td>
                            <div class="actions">
                                <button class="btn btn-secondary btn-sm" onclick="triggerSimulatedCall('${r.id}')"><i data-lucide="phone"></i> Call</button>
                                <button class="btn btn-secondary btn-sm btn-danger" onclick="deleteReminder('${r.id}')"><i data-lucide="trash-2"></i></button>
                            </div>
                        </td>
                    `;
                    tbody.appendChild(tr);
                });
            }
        }
        
        // 2. Render Full-width Scheduler Board View
        renderScheduleBoard(reminders);
        
        // 3. Render Dashboard Naye Cozy Schedule Panel
        renderTodayScheduleList();
        
        // 4. Render Caregiver Patients Board
        renderPatientsDashboard();
        
        // Dynamic Lucide rendering
        if (window.lucide) {
            lucide.createIcons();
        }
        
    } catch (err) {
        console.error("Error fetching reminders schedule:", err);
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="6" class="table-empty text-red">Failed to load schedule.</td></tr>`;
        }
    }
}

// Helpers for Mockup Cozy Visuals
function formatTime12h(timeStr) {
    if (!timeStr) return "12:00 PM";
    try {
        const parts = timeStr.split(":");
        const h = parseInt(parts[0]);
        const m = parts[1];
        const ampm = h >= 12 ? "PM" : "AM";
        const h12 = h % 12 === 0 ? 12 : h % 12;
        return `${h12}:${m} ${ampm}`;
    } catch (e) {
        return timeStr;
    }
}

function getPatientAvatar(name) {
    const key = (name || "").toLowerCase().trim();
    if (key.includes("mom") || key.includes("mother")) {
        return "https://images.unsplash.com/photo-1544005313-94ddf0286df2?q=80&w=120&auto=format&fit=crop";
    } else if (key.includes("grandpa") || key.includes("father") || key.includes("dad") || key.includes("grandfather")) {
        return "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?q=80&w=120&auto=format&fit=crop";
    } else if (key.includes("grandma") || key.includes("grandmother") || key.includes("nani") || key.includes("dadi")) {
        return "https://images.unsplash.com/photo-1508214751196-bcfd4ca60f91?q=80&w=120&auto=format&fit=crop";
    } else {
        return "https://images.unsplash.com/photo-1534528741775-53994a69daeb?q=80&w=120&auto=format&fit=crop";
    }
}

function getRelativeTime(timestamp) {
    if (!timestamp) return "Just now";
    try {
        const diffMs = new Date() - new Date(timestamp);
        const diffMins = Math.round(diffMs / 60000);
        if (diffMins < 1) return "Just now";
        if (diffMins < 60) return `${diffMins}m ago`;
        const diffHrs = Math.round(diffMins / 60);
        if (diffHrs < 24) return `${diffHrs}h ago`;
        return new Date(timestamp).toLocaleDateString(undefined, {month: 'short', day: 'numeric'});
    } catch (e) {
        return "Just now";
    }
}

function renderTodayScheduleList() {
    const container = document.getElementById("schedule-list-items");
    if (!container) return;
    
    container.innerHTML = "";
    const todayStr = new Date().toISOString().substring(0, 10);
    const todayLogs = cachedLogs.filter(l => l.timestamp && l.timestamp.startsWith(todayStr));
    
    if (cachedReminders.length === 0) {
        container.innerHTML = `<div class="empty-list-text">No medication reminders scheduled for today.</div>`;
        return;
    }
    
    cachedReminders.forEach(r => {
        const isTaken = todayLogs.some(l => l.reminder_id === r.id && ["TAKEN", "TAKEN_EARLIER"].includes(l.outcome));
        const isCalling = activeSessionsStatusCheck(r.id);
        
        let statusBtn = "";
        if (isTaken) {
            statusBtn = `<span class="btn-status status-taken"><i data-lucide="check"></i> Taken</span>`;
        } else if (isCalling) {
            statusBtn = `<span class="btn-status status-calling">Calling...</span>`;
        } else {
            statusBtn = `<button class="btn-status status-upcoming" onclick="triggerSimulatedCall('${r.id}')">Calling...</button>`;
        }
        
        const isNight = r.time >= "18:00" || r.time < "06:00";
        const item = document.createElement("div");
        item.className = "schedule-item-row";
        item.innerHTML = `
            <div class="schedule-time-box">
                <i data-lucide="${isNight ? 'moon' : 'sun'}" class="time-ico"></i>
                <span class="time-text">${formatTime12h(r.time)}</span>
            </div>
            <div class="schedule-med-info">
                <span class="med-name">${escapeHtml(r.medication)} ${escapeHtml(r.dosage)}</span>
                <span class="med-patient">1 Tablet</span>
            </div>
            <div class="schedule-status-action">
                ${statusBtn}
            </div>
        `;
        container.appendChild(item);
    });
}

function activeSessionsStatusCheck(reminderId) {
    if (typeof currentSession !== 'undefined' && currentSession && currentSession.session_id) {
        // Simple check if simulator active
        const simModal = document.getElementById("call-sim-modal");
        if (simModal && simModal.classList.contains("active")) {
            // Find active scheduled reminder
            const boardRows = document.querySelectorAll("#reminders-tbody tr");
            // Check if matches active session
            if (currentSession.medication && cachedReminders.some(r => r.id === reminderId && r.medication === currentSession.medication)) {
                return true;
            }
        }
    }
    return false;
}

function renderScheduleBoard(reminders) {
    const boardTbody = document.getElementById("schedule-board-tbody");
    if (!boardTbody) return;
    
    if (reminders.length === 0) {
        boardTbody.innerHTML = `
            <tr>
                <td colspan="7" class="table-empty">
                    No medication reminders configured. Click '+ Add Medication' to begin!
                </td>
            </tr>`;
        return;
    }
    
    boardTbody.innerHTML = "";
    reminders.forEach(r => {
        const tr = document.createElement("tr");
        const statusClass = r.active ? "online" : "offline";
        const statusLabel = r.active ? "ACTIVE" : "DISABLED";
        
        tr.innerHTML = `
            <td><strong>${escapeHtml(r.patient)}</strong></td>
            <td><span class="badge">${escapeHtml(r.medication)}</span></td>
            <td>${escapeHtml(r.dosage)}</td>
            <td><strong style="color:var(--clr-blue); font-size:14.5px;">${r.time}</strong></td>
            <td><span class="text-secondary">${r.next_run}</span></td>
            <td>
                <span class="badge-outcome outcome-${r.active ? 'taken' : 'failed'}" style="font-size: 11px;">
                    ${statusLabel}
                </span>
            </td>
            <td>
                <div class="actions">
                    <button class="btn btn-secondary btn-sm" onclick="triggerSimulatedCall('${r.id}')"><i data-lucide="phone"></i> Direct Call</button>
                    <button class="btn btn-secondary btn-sm btn-danger" onclick="deleteReminder('${r.id}')"><i data-lucide="trash-2"></i> Delete</button>
                </div>
            </td>
        `;
        boardTbody.appendChild(tr);
    });
}

async function loadLogs() {
    const logsFeed = document.getElementById("activity-logs-container");
    const logsTbody = document.getElementById("logs-table-tbody");
    
    try {
        const response = await fetch("/api/logs");
        const data = await response.json();
        cachedLogs = data.logs;
        
        // Scan for new escalation alerts to pop open sliding notification drawer
        if (typeof lastSeenLogId !== 'undefined' && lastSeenLogId > 0 && data.logs.length > 0) {
            const newEscalations = data.logs.filter(l => l.id > lastSeenLogId && l.escalation_tier >= 3);
            newEscalations.forEach(log => {
                triggerAlertDrawer(log);
            });
        }
        
        // Track the maximum log ID seen
        if (data.logs.length > 0) {
            const maxId = Math.max(...data.logs.map(l => l.id || 0));
            if (typeof lastSeenLogId !== 'undefined') {
                lastSeenLogId = maxId;
            }
        }
        
        // 1. Calculate and update cozy mockup Statistics panel
        updateMockupStats();
        
        // Update standard metric counts if elements exist
        const m = data.metrics;
        const totalCallsEl = document.getElementById("metric-calls");
        if (totalCallsEl) totalCallsEl.innerText = m.total_calls;
        
        const adherenceEl = document.getElementById("metric-adherence");
        if (adherenceEl) adherenceEl.innerText = m.adherence_rate;
        
        // 2. Render Cozy mockup Recent Activity panel
        renderRecentActivityList(data.logs);
        
        // 3. Render Standard Dashboard Live Feed Preview (backward compatibility fallback)
        if (logsFeed) {
            if (data.logs.length === 0) {
                logsFeed.innerHTML = `<div class="feed-empty">No activity logs recorded yet.</div>`;
            } else {
                logsFeed.innerHTML = "";
                const previewLogs = data.logs.slice(0, 5);
                previewLogs.forEach(log => {
                    const out = log.outcome;
                    const isAlert = ["MEDICAL_CONCERN", "REFUSED", "CONFUSED", "NO_RESPONSE_FAILED"].includes(out);
                    const item = document.createElement("div");
                    item.className = "feed-item";
                    if (out === "MEDICAL_CONCERN" || out === "NO_RESPONSE_FAILED" || out === "REFUSED") {
                        item.classList.add("alert-concern");
                    }
                    
                    const timeFormatted = log.timestamp ? log.timestamp.substring(11, 16) : "12:00";
                    const outcomeBadgeClass = getOutcomeBadgeClass(out);
                    
                    item.innerHTML = `
                        <div class="feed-header">
                            <span class="feed-meta"><strong>${escapeHtml(log.patient)}</strong> : ${escapeHtml(log.medication)}</span>
                            <span class="feed-time">${timeFormatted}</span>
                        </div>
                        <p class="feed-desc">${escapeHtml(log.summary)}</p>
                        <div class="feed-header">
                            <span class="badge-outcome ${outcomeBadgeClass}">${out.replace("_", " ")}</span>
                            ${isAlert ? `<span style="font-size: 11px; color: var(--clr-red); font-weight:600; display:inline-flex; align-items:center; gap:4px;"><i data-lucide="alert-circle" style="width:12px; height:12px; stroke-width:2.5px;"></i> Escalated</span>` : ""}
                        </div>
                    `;
                    logsFeed.appendChild(item);
                });
            }
        }
        
        // Compile full list for total metrics
        let totalAlerts = 0;
        data.logs.forEach(l => {
            if (["MEDICAL_CONCERN", "REFUSED", "CONFUSED", "NO_RESPONSE_FAILED"].includes(l.outcome)) {
                totalAlerts++;
            }
        });
        const alertsEl = document.getElementById("metric-alerts");
        if (alertsEl) alertsEl.innerText = totalAlerts;
        
        // 4. Render Full-width Audit Log View
        renderLogsBoard(data.logs);
        
        // 5. Render Caregiver Patients Board
        renderPatientsDashboard();
        
        // Dynamic Lucide rendering
        if (window.lucide) {
            lucide.createIcons();
        }
        
    } catch (err) {
        console.error("Error fetching caregiver activity logs:", err);
        logsFeed.innerHTML = `<div class="feed-empty text-red">Failed to load feed.</div>`;
    }
}

function renderLogsBoard(logs) {
    const logsTbody = document.getElementById("logs-table-tbody");
    if (!logsTbody) return;
    
    logsTbody.innerHTML = "";
    logs.forEach((log, index) => {
        const out = log.outcome;
        const timeStr = log.timestamp ? log.timestamp.replace("T", " ").substring(0, 16) : "Date N/A";
        const badgeClass = getOutcomeBadgeClass(out);
        
        // Primary Row
        const tr = document.createElement("tr");
        tr.style.cursor = "pointer";
        tr.onclick = () => toggleLogDetails(index);
        tr.innerHTML = `
            <td><span class="text-secondary" style="font-size:12.5px;">${timeStr}</span></td>
            <td><strong>${escapeHtml(log.patient)}</strong></td>
            <td><span class="badge">${escapeHtml(log.medication)} (${escapeHtml(log.dosage)})</span></td>
            <td><span class="badge-outcome ${badgeClass}">${out.replace("_", " ")}</span></td>
            <td><span class="text-secondary" style="font-size:13px; line-height:1.45;">${escapeHtml(log.summary)}</span></td>
            <td><button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); toggleLogDetails(${index})"><i data-lucide="eye"></i> Inspect</button></td>
        `;
        logsTbody.appendChild(tr);
        
        // Detailed Expandable Dialogue Transcript Row (Standard Card format)
        const detailTr = document.createElement("tr");
        detailTr.id = `log-detail-${index}`;
        detailTr.style.display = "none";
        
        // Formulate transcript bubbles list
        let transcriptHtml = "";
        if (log.transcript && log.transcript.length > 0) {
            log.transcript.forEach(t => {
                const bubbleClass = t.role === "Agent" ? "agent-bubble" : "patient-bubble";
                transcriptHtml += `
                    <div class="bubble ${bubbleClass}" style="margin-bottom: 8px; max-width: 75%; float: ${t.role === 'Agent' ? 'left' : 'right'}; clear: both;">
                        <strong>${t.role}:</strong> ${escapeHtml(t.text)}
                    </div>
                `;
            });
        } else {
            transcriptHtml = `<div class="text-secondary">No audio transcript recorded for this session.</div>`;
        }
        
        detailTr.innerHTML = `
            <td colspan="6" style="background-color: rgba(3, 7, 18, 0.45); padding: 20px;">
                <div style="border: 1px solid var(--border-glass); border-radius: 12px; padding: 20px; background-color:#0D111E;">
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px;">
                        <!-- Left: Core notes -->
                        <div>
                            <h4 style="color:var(--clr-primary); font-family:'Outfit'; margin-bottom:8px; font-weight:700;"><i data-lucide="shield-alert" style="width:14px; height:14px; display:inline-block; vertical-align:middle; margin-right:4px;"></i> Caregiver Audit Details</h4>
                            <p style="font-size: 13.5px; line-height: 1.6; margin-bottom: 12px;"><strong>Guardian Alert Note:</strong><br>${escapeHtml(log.guardian_note)}</p>
                            <p style="font-size: 13.5px; line-height: 1.6; margin-bottom: 15px;"><strong>Outcome:</strong> <span class="badge-outcome ${badgeClass}">${out.replace("_", " ")}</span></p>
                            
                            <!-- Premium Voice Recording Player -->
                            <div style="margin-top: 18px; border-top: 1px solid var(--border-glass); padding-top: 18px;">
                                <h4 style="color:var(--clr-primary); font-family:'Outfit'; margin-bottom:10px; font-weight:700; display:flex; align-items:center; gap:6px;"><i data-lucide="volume-2" style="width:16px; height:16px; color:var(--clr-primary);"></i> Call Recording Playback</h4>
                                <div class="audio-player-container" style="display:flex; align-items:center; gap:12px; margin-top:8px;">
                                    <audio controls src="/static/recordings/${log.id}.wav" style="width: 100%; height: 38px; border-radius: 12px; background: #030712; border: 1px solid rgba(197,160,89,0.15); outline: none;" aria-label="Simulated conversation playback"></audio>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Right: Scrolling Transcript Bubbles -->
                        <div style="border-left: 1px solid var(--border-glass); padding-left: 20px; max-height: 180px; overflow-y: auto;">
                            <h4 style="font-family:'Outfit'; margin-bottom:12px; font-weight:700;"><i data-lucide="message-square" style="width:14px; height:14px; display:inline-block; vertical-align:middle; margin-right:4px;"></i> Audio Dialogue Transcript</h4>
                            <div style="width: 100%; display: inline-block;">
                                ${transcriptHtml}
                            </div>
                        </div>
                    </div>
                </div>
            </td>
        `;
        logsTbody.appendChild(detailTr);
    });
}

function toggleLogDetails(index) {
    const detailRow = document.getElementById(`log-detail-${index}`);
    if (!detailRow) return;
    
    if (detailRow.style.display === "none") {
        detailRow.style.display = "table-row";
    } else {
        detailRow.style.display = "none";
    }
}

// --------------------------------------------------------------------------
// 2. Modals Control & Addition Form Handler
// --------------------------------------------------------------------------

function initModalControls() {
    const addModal = document.getElementById("add-reminder-modal");
    const openBtn = document.getElementById("btn-open-add-modal");
    const openBtnSchedule = document.getElementById("btn-open-add-modal-schedule");
    const closeBtn = document.getElementById("btn-close-add-modal");
    const cancelBtn = document.getElementById("btn-cancel-add");
    const form = document.getElementById("add-reminder-form");
    
    const open = () => addModal.classList.add("active");
    const close = () => {
        addModal.classList.remove("active");
        form.reset();
        const warningBanner = document.getElementById("ddi-form-warning");
        if (warningBanner) warningBanner.style.display = "none";
    };

    if (openBtn) openBtn.addEventListener("click", open);
    if (openBtnSchedule) openBtnSchedule.addEventListener("click", open);
    if (closeBtn) closeBtn.addEventListener("click", close);
    if (cancelBtn) cancelBtn.addEventListener("click", close);
    
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const payload = {
            patient: document.getElementById("input-patient").value.trim(),
            medication: document.getElementById("input-medication").value.trim(),
            dosage: document.getElementById("input-dosage").value.trim(),
            time: document.getElementById("input-time").value
        };
        
        try {
            const response = await fetch("/api/reminders", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const res = await response.json();
            
            if (res.status === "success") {
                const safety = res.safety || { safe: true, warnings: [] };
                
                if (!safety.safe) {
                    const warningBanner = document.getElementById("ddi-form-warning");
                    const warningText = document.getElementById("ddi-form-warning-text");
                    
                    if (warningBanner && warningText) {
                        warningText.innerText = safety.warnings.map(w => `${w.drug_a} + ${w.drug_b}: ${w.warning}`).join("\n");
                        warningBanner.style.display = "flex";
                        
                        const confirmAdd = confirm("Drug Conflict Warning!\n" + safety.warnings.map(w => w.warning).join("\n") + "\n\nAre you sure you want to schedule this medication?");
                        if (!confirmAdd) {
                            // Rollback added reminder
                            await fetch(`/api/reminders/${res.reminder.id}`, { method: "DELETE" });
                            return;
                        }
                    }
                }
                
                close();
                loadDashboardData();
            } else {
                alert(`Error: ${res.message}`);
            }
        } catch (err) {
            console.error("Error creating reminder:", err);
            alert("Connection error. Could not save reminder.");
        }
    });
}

async function deleteReminder(id) {
    if (!confirm("Are you sure you want to delete this scheduled medication?")) return;
    
    try {
        const response = await fetch(`/api/reminders/${id}`, { method: "DELETE" });
        const res = await response.json();
        
        if (res.status === "success") {
            loadDashboardData();
        } else {
            alert(`Error: ${res.message}`);
        }
    } catch (err) {
        console.error("Error deleting reminder:", err);
    }
}

// --------------------------------------------------------------------------
// 3. Interactive Call Simulator Engine (Live Session)
// --------------------------------------------------------------------------

let currentSession = {
    session_id: null,
    patient_name: "",
    medication: "",
    dosage: "",
    last_outcome: "OTHER",
    last_guardian_note: "Conversing with patient."
};

// High-Accessibility Focus Trapping Variables
let savedFocusElement = null;
let firstFocusableElement = null;
let lastFocusableElement = null;

function handleModalKeydown(e) {
    const modal = document.getElementById("call-sim-modal");
    if (!modal || !modal.classList.contains("active")) return;

    // ESC close key mapping
    if (e.key === "Escape" || e.keyCode === 27) {
        closeSimModal();
        return;
    }

    // TAB focus trapping
    if (e.key === "Tab" || e.keyCode === 9) {
        if (e.shiftKey) { // Backwards
            if (document.activeElement === firstFocusableElement) {
                lastFocusableElement.focus();
                e.preventDefault();
            }
        } else { // Forwards
            if (document.activeElement === lastFocusableElement) {
                firstFocusableElement.focus();
                e.preventDefault();
            }
        }
    }
}

function closeSimModal() {
    const modal = document.getElementById("call-sim-modal");
    if (!modal) return;
    
    modal.classList.remove("active");
    document.removeEventListener("keydown", handleModalKeydown);
    
    // Restore focus
    if (savedFocusElement) {
        savedFocusElement.focus();
    }
    
    loadDashboardData(); // Refresh caregiver metrics feed
}

async function triggerSimulatedCall(reminderId) {
    savedFocusElement = document.activeElement; // Track focus

    const simModal = document.getElementById("call-sim-modal");
    const feed = document.getElementById("sim-transcript-feed");
    const inputForm = document.getElementById("sim-input-form");
    const inputField = document.getElementById("sim-patient-input");
    const resultPanel = document.getElementById("sim-result-panel");
    const title = document.getElementById("sim-patient-title");
    
    // Clear feed & overlays
    feed.innerHTML = "";
    resultPanel.classList.remove("active");
    simModal.classList.add("active");
    inputField.disabled = false;
    document.getElementById("btn-send-sim").disabled = false;
    
    // Wire up accessible close button
    const closeBtn = document.getElementById("btn-close-sim-modal");
    if (closeBtn) {
        closeBtn.onclick = closeSimModal;
    }
    
    // Calculate focusable elements inside modal content
    const content = document.getElementById("sim-modal-content");
    if (content) {
        const focusables = content.querySelectorAll('a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), [tabindex="0"]');
        if (focusables.length > 0) {
            firstFocusableElement = focusables[0];
            lastFocusableElement = focusables[focusables.length - 1];
        }
    }
    
    // Announce to Screen Readers and Bind keypresses
    simModal.focus();
    document.addEventListener("keydown", handleModalKeydown);
    
    // Setup inputs listener
    inputForm.onsubmit = (e) => {
        e.preventDefault();
        const text = inputField.value.trim();
        if (text) {
            sendSimText(text);
        }
    };
    
    // Set mock ringing status text
    title.innerText = "Connecting call...";
    
    try {
        // Start check-in session in backend
        const response = await fetch("/api/simulate/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ reminder_id: reminderId })
        });
        const res = await response.json();
        
        if (res.status === "success") {
            // Load state
            currentSession.session_id = res.session_id;
            currentSession.patient_name = res.patient;
            currentSession.medication = res.medication;
            currentSession.dosage = res.dosage;
            currentSession.last_outcome = "OTHER";
            currentSession.last_guardian_note = "Conversing with patient.";
            
            // Re-render titles
            title.innerText = `Connected with ${res.patient}`;
            document.getElementById("sim-med-subtitle").innerText = `${res.medication} (${res.dosage}) Check-In`;
            
            // Append introductory greeting turn
            appendChatBubble("Agent", res.greeting);
            
        } else {
            alert(`Call connection error: ${res.message}`);
            closeSimModal();
        }
    } catch (err) {
        console.error("Error starting simulation session:", err);
        alert("Failed to start call simulator.");
        closeSimModal();
    }
}

async function sendSimText(text) {
    const feed = document.getElementById("sim-transcript-feed");
    const inputField = document.getElementById("sim-patient-input");
    const inputBtn = document.getElementById("btn-send-sim");
    
    if (!currentSession.session_id) return;
    
    // Append patient bubble
    appendChatBubble("Patient", text);
    inputField.value = "";
    
    // Lock controls during processing
    inputField.disabled = true;
    inputBtn.disabled = true;
    
    // Add quick typing indicator
    const typingBubble = appendChatBubble("Agent", "Thinking...", true);
    
    try {
        const response = await fetch("/api/simulate/turn", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                session_id: currentSession.session_id,
                patient_reply: text
            })
        });
        const res = await response.json();
        
        // Remove typing indicator
        typingBubble.remove();
        
        if (res.status === "success") {
            // Append agent reply
            appendChatBubble("Agent", res.spoken_reply);
            
            // Record last classified outcome
            currentSession.last_outcome = res.outcome;
            currentSession.last_guardian_note = res.guardian_note;
            
            if (res.end_call) {
                finishCallSimulation();
            } else {
                // Unlock inputs for next dialogue turn
                inputField.disabled = false;
                inputBtn.disabled = false;
                inputField.focus();
            }
        } else {
            appendChatBubble("Agent", "[API Error: Failed to process turn.]");
        }
    } catch (err) {
        console.error("Error processing simulation turn:", err);
        typingBubble.remove();
        appendChatBubble("Agent", "[Connection Error: Could not reach agent.]");
    }
}

async function finishCallSimulation() {
    const resultPanel = document.getElementById("sim-result-panel");
    const badge = document.getElementById("sim-result-badge");
    const summaryField = document.getElementById("sim-result-summary");
    
    // Set loader status
    badge.innerText = currentSession.last_outcome.replace("_", " ");
    badge.className = `result-status-badge ${getOutcomeBadgeClass(currentSession.last_outcome)}`;
    summaryField.innerText = "Call finished. Generating guardian summary...";
    resultPanel.classList.add("active");
    
    // Listener to close sim modal
    document.getElementById("btn-close-sim-panel").onclick = () => {
        closeSimModal();
        resultPanel.classList.remove("active");
    };
    
    try {
        // Finalize call on server
        const response = await fetch("/api/simulate/end", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                session_id: currentSession.session_id,
                outcome: currentSession.last_outcome,
                guardian_note: currentSession.last_guardian_note
            })
        });
        const res = await response.json();
        
        if (res.status === "success") {
            // Display caregiver summary
            summaryField.innerHTML = `
                <strong>Outcome:</strong> ${currentSession.last_outcome.replace("_", " ")}<br>
                <strong>Guardian Note:</strong> ${currentSession.last_guardian_note}<br><br>
                <strong>Summary Report:</strong><br>${escapeHtml(res.summary)}
            `;
        } else {
            summaryField.innerText = "Error finalizing log metrics.";
        }
    } catch (err) {
        console.error("Error ending simulation session:", err);
        summaryField.innerText = "Connection error while finalizing call logs.";
    }
}

// --------------------------------------------------------------------------
// 4. Single Page Application (SPA) Tab Switcher
// --------------------------------------------------------------------------

function initTabSwitcher() {
    const tabs = [
        { id: "nav-dashboard", viewId: "view-dashboard", title: "Care Portal", subtitle: "Real-time medication adherence & proactive patient diagnostics" },
        { id: "nav-insights", viewId: "view-insights", title: "Clinical Insights", subtitle: "Machine learning risk forecasts, cognitive trends, and emergency escalations" },
        { id: "nav-reminders", viewId: "view-schedule", title: "Medication Scheduler", subtitle: "Manage active schedules, patient details, and background reminder alerts" },
        { id: "nav-activity", viewId: "view-activity", title: "Audit Log Database", subtitle: "Review call outcomes, detailed transcripts, and historical adherence tracking" },
        { id: "nav-patients", viewId: "view-patients", title: "Patients Dashboard", subtitle: "Patient profiles, clinical summaries, individual adherence, and cognitive monitoring" }
    ];

    tabs.forEach(t => {
        const link = document.getElementById(t.id);
        if (!link) return;

        link.onclick = (e) => {
            e.preventDefault();
            
            // Remove active classes from all links
            tabs.forEach(x => {
                const el = document.getElementById(x.id);
                const panel = document.getElementById(x.viewId);
                if (el) el.classList.remove("active");
                if (panel) panel.style.display = "none";
            });

            // Set current tab active
            link.classList.add("active");
            const panel = document.getElementById(t.viewId);
            if (panel) panel.style.display = "block";
            
            // Update Page headers dynamically
            document.getElementById("view-title").innerText = t.title;
            document.getElementById("view-subtitle").innerText = t.subtitle;

            // Instantly sync data
            loadDashboardData();
        };
    });
}

// --------------------------------------------------------------------------
// 5. GUI Filters & Autocomplete Helpers
// --------------------------------------------------------------------------

function filterScheduleTable() {
    const query = document.getElementById("schedule-search").value.toLowerCase().trim();
    const rows = document.querySelectorAll("#schedule-board-tbody tr");
    
    rows.forEach(row => {
        const text = row.innerText.toLowerCase();
        if (text.includes(query)) {
            row.style.display = "table-row";
        } else {
            row.style.display = "none";
        }
    });
}

function filterLogsTable() {
    const query = document.getElementById("log-search").value.toLowerCase().trim();
    const outcomeFilter = document.getElementById("log-outcome-filter").value;
    const tbody = document.getElementById("logs-table-tbody");
    
    // We filter from cached logs and redraw the list! This is fast and has zero server overhead!
    const filtered = cachedLogs.filter(log => {
        const matchesQuery = !query || 
            log.patient.toLowerCase().includes(query) || 
            log.medication.toLowerCase().includes(query) || 
            log.summary.toLowerCase().includes(query);
            
        const matchesOutcome = outcomeFilter === "ALL" || log.outcome === outcomeFilter;
        
        return matchesQuery && matchesOutcome;
    });
    
    renderLogsBoard(filtered);
}

async function updateSystemStatus() {
    const indicator = document.getElementById("system-status-indicator");
    const textEl = document.getElementById("system-status-text");
    if (!indicator || !textEl) return;
    
    try {
        const response = await fetch("/api/status");
        const data = await response.json();
        
        if (data.status === "success") {
            const provider = data.api_provider ? data.api_provider.toUpperCase() : "MOCK";
            if (data.api_connected) {
                indicator.className = "status-indicator online";
                textEl.innerText = `${provider} Active`;
                textEl.title = `Model: ${data.model_name}\nScheduler: ${data.scheduler_active ? 'Online' : 'Offline'}\nTally: ${data.tally_online ? 'Online' : 'Offline'}`;
            } else {
                indicator.className = "status-indicator snooze"; // amber style
                textEl.innerText = "Offline Mock Active";
                textEl.title = "No API keys configured. Simulating conversation locally.";
            }
        }
    } catch (err) {
        console.error("Error updating system status:", err);
        indicator.className = "status-indicator offline";
        textEl.innerText = "System Offline";
    }
}

// Call status updater
updateSystemStatus();
setInterval(updateSystemStatus, 15000);

// --------------------------------------------------------------------------
// 6. GUI Helper Utilities
// --------------------------------------------------------------------------

function appendChatBubble(role, text, isTemp = false) {
    const feed = document.getElementById("sim-transcript-feed");
    const bubble = document.createElement("div");
    bubble.className = `bubble ${role === "Agent" ? "agent-bubble" : "patient-bubble"}`;
    bubble.innerText = text;
    feed.appendChild(bubble);
    
    // Smooth scrolling auto-fit
    feed.parentElement.scrollTop = feed.parentElement.scrollHeight;
    
    return bubble;
}

function getOutcomeBadgeClass(outcome) {
    const map = {
        "TAKEN": "outcome-taken",
        "TAKEN_EARLIER": "outcome-earlier",
        "SNOOZE": "outcome-snooze",
        "REFUSED": "outcome-refused",
        "CONFUSED": "outcome-confused",
        "MEDICAL_CONCERN": "outcome-concern",
        "NO_RESPONSE_FAILED": "outcome-failed",
        "NO_RESPONSE": "outcome-snooze",
        "OTHER": "outcome-other"
    };
    return map[outcome] || "outcome-other";
}

function escapeHtml(str) {
    if (!str) return "";
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Global scope helpers for onclick attributes in quick choice pills
window.sendSimText = sendSimText;
window.toggleLogDetails = toggleLogDetails;
window.filterScheduleTable = filterScheduleTable;
window.filterLogsTable = filterLogsTable;

// --------------------------------------------------------------------------
// 7. Clinical Analytics & Heatmap Render Engines
// --------------------------------------------------------------------------

let cachedRiskScores = {};

async function loadRiskScores() {
    try {
        const response = await fetch("/api/analytics/risk");
        const risks = await response.json();
        cachedRiskScores = risks;
        
        updateTableRiskBadges();
    } catch (err) {
        console.error("Error loading risk scores:", err);
    }
}

function updateTableRiskBadges() {
    // Inject into active reminders table
    const dashboardRows = document.querySelectorAll("#reminders-tbody tr");
    dashboardRows.forEach(row => {
        const deleteBtn = row.querySelector("button[onclick^='deleteReminder']");
        if (deleteBtn) {
            const onclickText = deleteBtn.getAttribute("onclick");
            const match = onclickText.match(/'([^']+)'/);
            if (match && match[1]) {
                const rId = match[1];
                const riskInfo = cachedRiskScores[rId] || { risk_score: 0.15, level: "Low" };
                injectRiskBadge(row, riskInfo, 5); // Insert at index 5 before actions column
            }
        }
    });

    // Inject into scheduler board table
    const boardRows = document.querySelectorAll("#schedule-board-tbody tr");
    boardRows.forEach(row => {
        const deleteBtn = row.querySelector("button[onclick^='deleteReminder']");
        if (deleteBtn) {
            const onclickText = deleteBtn.getAttribute("onclick");
            const match = onclickText.match(/'([^']+)'/);
            if (match && match[1]) {
                const rId = match[1];
                const riskInfo = cachedRiskScores[rId] || { risk_score: 0.15, level: "Low" };
                injectRiskBadge(row, riskInfo, 5); // Insert at index 5 before active column
            }
        }
    });
}

function injectRiskBadge(row, riskInfo, insertIndex) {
    let riskCell = row.querySelector(".risk-td");
    if (!riskCell) {
        riskCell = document.createElement("td");
        riskCell.className = "risk-td";
        const refNode = row.children[insertIndex];
        row.insertBefore(riskCell, refNode);
    }
    
    const risk = riskInfo.risk_score;
    const level = riskInfo.level;
    let badgeClass = "outcome-taken";
    if (level === "High") badgeClass = "outcome-refused";
    else if (level === "Medium") badgeClass = "outcome-concern";
    
    riskCell.innerHTML = `
        <span class="badge-outcome ${badgeClass}" style="display:inline-flex; align-items:center; gap:6px; font-weight:700; font-size:11.5px; border:1px solid rgba(255,255,255,0.05); padding: 4px 10px;">
            <span class="pulse-indicator status-${level.toLowerCase()}" style="width:7px; height:7px; border-radius:50%; display:inline-block; box-shadow:0 0 8px currentColor;"></span>
            ${level} (${Math.round(risk * 100)}%)
        </span>
    `;
}

let currentInsightsPatient = "Grandpa";

async function loadInsightsData() {
    const patientName = currentInsightsPatient;
    
    try {
        const response = await fetch(`/api/analytics/cognitive/${patientName}`);
        const data = await response.json();
        
        // Show/hide decline alert card
        const declineBanner = document.getElementById("cognitive-decline-banner");
        if (declineBanner) {
            declineBanner.style.display = data.decline_flag ? "flex" : "none";
        }
        
        renderCognitiveTrendChart(data.trend);
        renderAdherenceHeatmap(data.trend);
        loadEscalationTimeline();
        
    } catch (err) {
        console.error("Error loading clinical insights:", err);
    }
}

function renderCognitiveTrendChart(trend) {
    const canvas = document.getElementById("cognitiveTrendChart");
    if (!canvas) return;
    
    const ctx = canvas.getContext("2d");
    const rect = canvas.getBoundingClientRect();
    
    // Auto-adjust relative pixel display for clean lines
    canvas.width = rect.width * window.devicePixelRatio;
    canvas.height = rect.height * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    
    const width = rect.width;
    const height = rect.height;
    
    ctx.clearRect(0, 0, width, height);
    
    const scores = trend.coherence_scores || [];
    const latencies = trend.response_latencies || [];
    const labels = trend.timestamps || [];
    const count = scores.length;
    
    if (count === 0) {
        ctx.fillStyle = "#9CA3AF";
        ctx.font = "13px 'Plus Jakarta Sans'";
        ctx.textAlign = "center";
        ctx.fillText("No cognitive trend logs available.", width / 2, height / 2);
        return;
    }
    
    const paddingLeft = 45;
    const paddingRight = 45;
    const paddingTop = 20;
    const paddingBottom = 30;
    
    const chartW = width - paddingLeft - paddingRight;
    const chartH = height - paddingTop - paddingBottom;
    
    // Draw Grid Lines (Horizontal)
    const gridRows = 4;
    ctx.strokeStyle = "rgba(255, 255, 255, 0.04)";
    ctx.lineWidth = 1;
    for (let i = 0; i <= gridRows; i++) {
        const y = paddingTop + (chartH / gridRows) * i;
        ctx.beginPath();
        ctx.moveTo(paddingLeft, y);
        ctx.lineTo(width - paddingRight, y);
        ctx.stroke();
    }
    
    const getX = (index) => {
        if (count === 1) return paddingLeft + chartW / 2;
        return paddingLeft + (chartW / (count - 1)) * index;
    };
    
    const getYCoherence = (val) => {
        return paddingTop + chartH - (chartH * val);
    };
    
    const getYLatency = (val) => {
        const maxLatency = 15.0;
        const normalized = Math.min(val, maxLatency) / maxLatency;
        return paddingTop + chartH - (chartH * normalized);
    };
    
    // 1. Draw Coherence Line (Indigo Accent)
    ctx.strokeStyle = "#6366F1";
    ctx.lineWidth = 3.5;
    ctx.lineJoin = "round";
    ctx.shadowColor = "rgba(99, 102, 241, 0.3)";
    ctx.shadowBlur = 6;
    
    ctx.beginPath();
    scores.forEach((s, idx) => {
        const x = getX(idx);
        const y = getYCoherence(s);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();
    
    ctx.shadowBlur = 0; // Reset shadow
    
    scores.forEach((s, idx) => {
        ctx.fillStyle = "#6366F1";
        ctx.beginPath();
        ctx.arc(getX(idx), getYCoherence(s), 4.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#FFFFFF";
        ctx.beginPath();
        ctx.arc(getX(idx), getYCoherence(s), 2, 0, Math.PI * 2);
        ctx.fill();
    });
    
    // 2. Draw Latency Line (Amber Accent)
    ctx.strokeStyle = "#F59E0B";
    ctx.lineWidth = 2.5;
    ctx.lineJoin = "round";
    ctx.shadowColor = "rgba(245, 158, 11, 0.2)";
    ctx.shadowBlur = 5;
    
    ctx.beginPath();
    latencies.forEach((l, idx) => {
        const x = getX(idx);
        const y = getYLatency(l);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();
    
    ctx.shadowBlur = 0; // Reset shadow
    
    latencies.forEach((l, idx) => {
        ctx.fillStyle = "#F59E0B";
        ctx.beginPath();
        ctx.arc(getX(idx), getYLatency(l), 3.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#FFFFFF";
        ctx.beginPath();
        ctx.arc(getX(idx), getYLatency(l), 1.5, 0, Math.PI * 2);
        ctx.fill();
    });
    
    // 3. Draw Axis Labels
    ctx.fillStyle = "#9CA3AF";
    ctx.font = "9px 'Plus Jakarta Sans'";
    
    // Y-Axis labels Left (Coherence)
    ctx.textAlign = "right";
    ctx.fillText("100%", paddingLeft - 8, getYCoherence(1.0) + 3);
    ctx.fillText("50%", paddingLeft - 8, getYCoherence(0.5) + 3);
    ctx.fillText("0%", paddingLeft - 8, getYCoherence(0.0) + 3);
    
    // Y-Axis labels Right (Latency)
    ctx.textAlign = "left";
    ctx.fillText("0s", width - paddingRight + 8, getYLatency(0.0) + 3);
    ctx.fillText("7s", width - paddingRight + 8, getYLatency(7.5) + 3);
    ctx.fillText("15s", width - paddingRight + 8, getYLatency(15.0) + 3);
    
    // X-Axis labels
    ctx.textAlign = "center";
    const skip = Math.max(1, Math.floor(count / 5));
    labels.forEach((l, idx) => {
        if (idx % skip === 0) {
            ctx.fillText(l.split(" ")[0], getX(idx), height - paddingBottom + 16);
        }
    });
}

function renderAdherenceHeatmap(trend) {
    const grid = document.getElementById("adherence-heatmap-grid");
    if (!grid) return;
    
    grid.innerHTML = "";
    
    const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const outcomes = trend.outcomes || [];
    const timestamps = trend.timestamps || [];
    
    // Create 7x24 grid (Day indices 0-6 vs Hours 0-23)
    const matrix = Array(7).fill(null).map(() => Array(24).fill(null));
    
    timestamps.forEach((ts, idx) => {
        try {
            const parts = ts.split(" ");
            const dateParts = parts[0].split("-");
            const timeParts = parts[1].split(":");
            
            const date = new Date(new Date().getFullYear(), parseInt(dateParts[0]) - 1, parseInt(dateParts[1]), parseInt(timeParts[0]));
            matrix[date.getDay()][date.getHours()] = outcomes[idx];
        } catch (e) {
            // Safe random distribution to visual presentation during offline/mock state
            const seedDay = (idx * 3) % 7;
            const seedHour = (idx * 7 + 9) % 24;
            matrix[seedDay][seedHour] = outcomes[idx];
        }
    });
    
    // Redraw grid elements
    for (let day = 0; day < 7; day++) {
        const dayLabel = document.createElement("div");
        dayLabel.className = "heatmap-day-label";
        dayLabel.innerText = days[day];
        dayLabel.style.fontSize = "11.5px";
        dayLabel.style.color = "var(--txt-secondary)";
        dayLabel.style.fontWeight = "600";
        grid.appendChild(dayLabel);
        
        for (let hour = 0; hour < 24; hour++) {
            const cell = document.createElement("div");
            const outcome = matrix[day][hour];
            
            cell.className = "heatmap-cell";
            cell.style.width = "10.5px";
            cell.style.height = "10.5px";
            cell.style.borderRadius = "2.5px";
            cell.style.background = "rgba(255, 255, 255, 0.04)";
            
            if (outcome) {
                const badgeClass = getOutcomeBadgeClass(outcome);
                cell.classList.add(badgeClass);
                cell.title = `${days[day]} ${hour}:00 - ${outcome.replace("_", " ")}`;
                
                // Color override map based on badge outcomes
                if (badgeClass === "outcome-taken") cell.style.background = "var(--clr-green)";
                else if (badgeClass === "outcome-earlier") cell.style.background = "var(--clr-blue)";
                else if (badgeClass === "outcome-snooze") cell.style.background = "var(--clr-amber)";
                else if (badgeClass === "outcome-refused" || badgeClass === "outcome-failed") cell.style.background = "var(--clr-red)";
                else cell.style.background = "var(--clr-purple)";
            } else {
                cell.title = `No activity logged at ${days[day]} ${hour}:00`;
            }
            grid.appendChild(cell);
        }
    }
}

async function loadEscalationTimeline() {
    const container = document.getElementById("escalation-timeline-container");
    if (!container) return;
    
    try {
        const response = await fetch("/api/escalation/history");
        const escalations = await response.json();
        
        if (escalations.length === 0) {
            container.innerHTML = `<div class="timeline-empty">No critical alert escalation events logged.</div>`;
            return;
        }
        
        container.innerHTML = "";
        escalations.forEach(ev => {
            const timeStr = ev.timestamp ? ev.timestamp.replace("T", " ").substring(0, 16) : "Date N/A";
            const node = document.createElement("div");
            node.className = "timeline-node";
            node.style.display = "flex";
            node.style.gap = "15px";
            node.style.marginBottom = "15px";
            node.style.paddingLeft = "10px";
            node.style.borderLeft = "2.5px solid var(--clr-amber)";
            
            let colorClass = "outcome-snooze";
            if (ev.tier === 4) {
                node.style.borderLeftColor = "var(--clr-red)";
                colorClass = "outcome-refused";
            }
            
            node.innerHTML = `
                <div style="flex-shrink:0; font-size:11.5px; color:var(--txt-muted); min-width:85px;">${timeStr}</div>
                <div>
                    <span class="badge-outcome ${colorClass}" style="font-size:10px; padding:2px 6px;">Tier ${ev.tier} Alert</span>
                    <h4 style="font-size:13.5px; font-weight:700; color:var(--txt-primary); margin: 4px 0;">Alert for ${escapeHtml(ev.patient)} (${escapeHtml(ev.medication)})</h4>
                    <p style="font-size:12.5px; color:var(--txt-secondary); line-height:1.4;">${escapeHtml(ev.guardian_note)}</p>
                </div>
            `;
            container.appendChild(node);
        });
        
    } catch (err) {
        console.error("Error loading timeline history:", err);
    }
}

function initEscalationModal() {
    const modal = document.getElementById("test-escalation-modal");
    const openBtn = document.getElementById("btn-test-escalation-modal-open");
    const closeBtn = document.getElementById("btn-close-test-escalation");
    const cancelBtn = document.getElementById("btn-cancel-test-escalation");
    const form = document.getElementById("test-escalation-form");
    
    if (!modal) return;
    
    const open = () => modal.classList.add("active");
    const close = () => {
        modal.classList.remove("active");
        form.reset();
    };
    
    if (openBtn) openBtn.onclick = open;
    if (closeBtn) closeBtn.onclick = close;
    if (cancelBtn) cancelBtn.onclick = close;
    
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const payload = {
            patient: document.getElementById("test-patient").value.trim(),
            medication: document.getElementById("test-med").value.trim(),
            outcome: document.getElementById("test-outcome").value,
            custom_note: document.getElementById("test-note").value.trim()
        };
        
        try {
            const response = await fetch("/api/escalation/test", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const res = await response.json();
            
            if (res.status === "success") {
                close();
                // Dynamically trigger sliding drawer alerts for offline demo flow!
                const alertLog = {
                    patient: payload.patient,
                    medication: payload.medication,
                    dosage: payload.dosage || "10mg",
                    outcome: payload.outcome,
                    guardian_note: payload.custom_note || "Test alert triggered from dashboard."
                };
                triggerAlertDrawer(alertLog);
                loadInsightsData();
            } else {
                alert(`Error: ${res.message}`);
            }
        } catch (err) {
            console.error("Error triggering test alert:", err);
        }
    });
}

// ==========================================================================
// 8. Gold-Cozy Mockup Visual Controllers & Sparkline Drawer
// ==========================================================================

function updateMockupStats() {
    const totalEl = document.getElementById("metric-reminders-total");
    const completedEl = document.getElementById("metric-reminders-completed");
    const completedPctEl = document.getElementById("metric-reminders-completed-pct");
    const missedEl = document.getElementById("metric-reminders-missed");
    const missedPctEl = document.getElementById("metric-reminders-missed-pct");
    const pendingEl = document.getElementById("metric-reminders-pending");
    const pendingPctEl = document.getElementById("metric-reminders-pending-pct");
    
    if (!totalEl) return; // Mockup view not active/visible
    
    const todayStr = new Date().toISOString().substring(0, 10);
    const todayLogs = cachedLogs.filter(l => l.timestamp && l.timestamp.startsWith(todayStr));
    
    const completed = todayLogs.filter(l => ["TAKEN", "TAKEN_EARLIER"].includes(l.outcome)).length;
    const missed = todayLogs.filter(l => ["REFUSED", "NO_RESPONSE_FAILED", "MEDICAL_CONCERN", "CONFUSED"].includes(l.outcome)).length;
    
    const total = cachedReminders.length + completed + missed;
    const pending = Math.max(0, cachedReminders.length);
    
    totalEl.innerText = total;
    completedEl.innerText = completed;
    completedPctEl.innerText = total > 0 ? `${Math.round((completed / total) * 100)}%` : "0%";
    
    missedEl.innerText = missed;
    missedPctEl.innerText = total > 0 ? `${Math.round((missed / total) * 100)}%` : "0%";
    
    pendingEl.innerText = pending;
    pendingPctEl.innerText = total > 0 ? `${Math.round((pending / total) * 100)}%` : "0%";
    
    // Draw mini sparks sparkline
    drawMiniInsightChart();
    
    // Sync text
    const statsTextEl = document.getElementById("insight-stats-text");
    if (statsTextEl && total > 0) {
        statsTextEl.innerText = `Great job! ${Math.round((completed / total) * 100)}% medications completed today.`;
    }
}

function renderRecentActivityList(logs) {
    const container = document.getElementById("dashboard-recent-activities");
    if (!container) return;
    
    container.innerHTML = "";
    const preview = logs.slice(0, 3); // Get top 3
    
    if (preview.length === 0) {
        container.innerHTML = `<div class="empty-list-text">No recent patient activities logged.</div>`;
        return;
    }
    
    preview.forEach(log => {
        const avatar = getPatientAvatar(log.patient);
        const relTime = getRelativeTime(log.timestamp);
        const out = log.outcome;
        
        let statusTag = "";
        if (["TAKEN", "TAKEN_EARLIER"].includes(out)) {
            statusTag = `<span class="activity-status tag-success">Completed</span>`;
        } else if (["NO_RESPONSE", "SNOOZE"].includes(out)) {
            statusTag = `<span class="activity-status tag-progress">In Progress</span>`;
        } else {
            statusTag = `<span class="activity-status tag-failed">${out.replace("_", " ")}</span>`;
        }
        
        const item = document.createElement("div");
        item.className = "activity-item-row";
        item.innerHTML = `
            <img src="${avatar}" alt="${escapeHtml(log.patient)}" class="patient-avatar-circle">
            <div class="activity-details">
                <div class="activity-detail-header">
                    <span class="activity-p-name">${escapeHtml(log.patient)}</span>
                    ${statusTag}
                </div>
                <span class="activity-description">${escapeHtml(log.medication)} ${escapeHtml(log.dosage)} - ${formatTime12h(log.scheduled_time)}</span>
                <span class="activity-agent-speech">${escapeHtml(log.summary)}</span>
            </div>
            <span class="activity-time-lbl">${relTime}</span>
        `;
        container.appendChild(item);
    });
}

function drawMiniInsightChart() {
    const canvas = document.getElementById("miniInsightChart");
    if (!canvas) return;
    
    const ctx = canvas.getContext("2d");
    
    // Auto-adjust scale
    const rect = canvas.getBoundingClientRect();
    canvas.width = 60 * window.devicePixelRatio;
    canvas.height = 35 * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    
    ctx.clearRect(0, 0, 60, 35);
    
    ctx.strokeStyle = "#c5a059";
    ctx.lineWidth = 2.5;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    
    ctx.beginPath();
    ctx.moveTo(5, 30);
    ctx.lineTo(15, 20);
    ctx.lineTo(25, 25);
    ctx.lineTo(35, 10);
    ctx.lineTo(45, 15);
    ctx.lineTo(55, 5);
    ctx.stroke();
    
    ctx.fillStyle = "#c5a059";
    ctx.beginPath();
    ctx.arc(55, 5, 3.2, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(55, 5, 1.2, 0, Math.PI * 2);
    ctx.fill();
}

function initMockupBindings() {
    // Nav viewall schedule
    const navSchedBtn = document.getElementById("nav-to-schedule-tab");
    if (navSchedBtn) {
        navSchedBtn.onclick = () => {
            const schedTab = document.getElementById("nav-reminders");
            if (schedTab) schedTab.click();
        };
    }
    
    // Nav viewall activity
    const navActivityBtn = document.getElementById("nav-to-logs-tab");
    if (navActivityBtn) {
        navActivityBtn.onclick = () => {
            const activityTab = document.getElementById("nav-activity");
            if (activityTab) activityTab.click();
        };
    }
    
    // Quick Add Reminder button
    const quickAddBtn = document.getElementById("btn-quick-add-reminder");
    if (quickAddBtn) {
        quickAddBtn.onclick = () => {
            const addBtn = document.getElementById("btn-open-add-modal");
            if (addBtn) addBtn.click();
        };
    }
    
    // Quick Place Call button
    const quickCallBtn = document.getElementById("btn-quick-place-call");
    if (quickCallBtn) {
        quickCallBtn.onclick = () => {
            triggerSimulatedCall("mock-test");
        };
    }
    
    // Quick View Patients button
    const quickPatientsBtn = document.getElementById("btn-quick-view-patients");
    if (quickPatientsBtn) {
        quickPatientsBtn.onclick = () => {
            const patientsTab = document.getElementById("nav-patients");
            if (patientsTab) patientsTab.click();
        };
    }
    
    // Quick Reports button
    const quickReportsBtn = document.getElementById("btn-quick-reports");
    if (quickReportsBtn) {
        quickReportsBtn.onclick = () => {
            const insightsTab = document.getElementById("nav-insights");
            if (insightsTab) insightsTab.click();
        };
    }
}

// ==========================================================================
// 9. Caregiver Multi-Patient Profile Grid Rendering & Logic
// ==========================================================================

let patientCognitiveStatus = {};

function renderPatientsDashboard() {
    const container = document.getElementById("patients-cards-container");
    if (!container) return;
    
    // Aggregate unique patient names
    const defaultPatients = ["Grandpa", "Mom", "Grandma"];
    const patientNameMap = new Map();
    defaultPatients.forEach(p => patientNameMap.set(p.toLowerCase(), p));
    cachedReminders.forEach(r => {
        if (r.patient) patientNameMap.set(r.patient.toLowerCase().trim(), r.patient.trim());
    });
    cachedLogs.forEach(l => {
        if (l.patient) patientNameMap.set(l.patient.toLowerCase().trim(), l.patient.trim());
    });
    const patientNames = Array.from(patientNameMap.values());
    
    container.innerHTML = "";
    
    patientNames.forEach(name => {
        // Asynchronously fetch cognitive trend data if not already cached
        if (!patientCognitiveStatus[name]) {
            patientCognitiveStatus[name] = { loading: true, decline_flag: false };
            fetchPatientCognitiveData(name);
        }
        
        const pReminders = cachedReminders.filter(r => r.patient.toLowerCase().trim() === name.toLowerCase().trim());
        const pLogs = cachedLogs.filter(l => l.patient.toLowerCase().trim() === name.toLowerCase().trim());
        
        // Calculate statistics
        const totalCalls = pLogs.length;
        const takenCalls = pLogs.filter(l => ["TAKEN", "TAKEN_EARLIER"].includes(l.outcome)).length;
        const adherenceRate = totalCalls > 0 ? Math.round((takenCalls / totalCalls) * 100) : 100; // Baseline to 100 if no calls yet
        
        // Get latest coherence
        let latestCoherence = 100;
        if (pLogs.length > 0) {
            const sortedLogs = [...pLogs].sort((a,b) => new Date(a.timestamp) - new Date(b.timestamp));
            const lastLog = sortedLogs[sortedLogs.length - 1];
            if (lastLog && lastLog.coherence_score !== undefined && lastLog.coherence_score !== null) {
                latestCoherence = Math.round(lastLog.coherence_score * 100);
            }
        }
        
        // Get average latency
        let avgLatency = "N/A";
        const logsWithLatency = pLogs.filter(l => l.response_latency_sec !== undefined && l.response_latency_sec !== null);
        if (logsWithLatency.length > 0) {
            const sumLatency = logsWithLatency.reduce((sum, l) => sum + l.response_latency_sec, 0);
            avgLatency = `${(sumLatency / logsWithLatency.length).toFixed(1)}s`;
        }
        
        // Fetch cached cognitive status
        const cognitiveData = patientCognitiveStatus[name];
        const hasDecline = cognitiveData && cognitiveData.decline_flag;
        
        // Build meds list
        let medsListHtml = "";
        if (pReminders.length === 0) {
            medsListHtml = `<div class="empty-list-text" style="font-size:11px; padding: 4px 0;">No active scheduled medications.</div>`;
        } else {
            pReminders.forEach(r => {
                const isNight = r.time >= "18:00" || r.time < "06:00";
                medsListHtml += `
                    <div class="patient-med-row">
                        <span class="patient-med-name">${escapeHtml(r.medication)} (${escapeHtml(r.dosage)})</span>
                        <span class="patient-med-time">
                            <i data-lucide="${isNight ? 'moon' : 'sun'}"></i> ${formatTime12h(r.time)}
                        </span>
                    </div>
                `;
            });
        }
        
        // Set dynamic avatar
        const avatarUrl = getPatientAvatar(name);
        
        // Create card element
        const card = document.createElement("div");
        card.className = "patient-profile-card";
        if (hasDecline) {
            card.classList.add("patient-decline-card-border");
        }
        
        // Warning Banner if decline detected
        const warningBannerHtml = hasDecline ? `
            <div class="patient-decline-card-alert">
                <i data-lucide="shield-alert" class="alert-ico-pulse"></i>
                <span>Potential Cognitive Health Decline Detected</span>
            </div>
        ` : "";
        
        card.innerHTML = `
            ${warningBannerHtml}
            <div class="patient-card-header">
                <img src="${avatarUrl}" alt="${escapeHtml(name)}" class="patient-card-avatar">
                <div class="patient-card-identity">
                    <span class="patient-card-name">${escapeHtml(name)}</span>
                    <span class="patient-card-role">Family Member</span>
                </div>
            </div>
            
            <div class="patient-stats-grid">
                <div class="patient-stat-item">
                    <span class="patient-stat-lbl">Adherence</span>
                    <span class="patient-stat-val ${adherenceRate >= 80 ? 'text-green' : adherenceRate >= 50 ? 'text-amber' : 'text-red'}">${adherenceRate}%</span>
                </div>
                <div class="patient-stat-item">
                    <span class="patient-stat-lbl">Coherence</span>
                    <span class="patient-stat-val ${latestCoherence >= 80 ? 'text-green' : latestCoherence >= 50 ? 'text-amber' : 'text-red'}">${latestCoherence}%</span>
                </div>
                <div class="patient-stat-item">
                    <span class="patient-stat-lbl">Latency</span>
                    <span class="patient-stat-val">${avgLatency}</span>
                </div>
            </div>
            
            <div class="patient-meds-section">
                <h4 style="font-size: 11px; font-weight:700; color:var(--txt-secondary); text-transform:uppercase; margin-bottom:8px; letter-spacing:0.5px;">Medication Schedule</h4>
                <div class="patient-meds-list">
                    ${medsListHtml}
                </div>
            </div>
            
            <div class="patient-card-actions">
                <button class="btn btn-secondary btn-sm" onclick="triggerPatientSimCall('${escapeHtml(name)}')">
                    <i data-lucide="phone"></i> Call Next Dose
                </button>
                <button class="btn btn-primary btn-sm btn-header" onclick="viewPatientInsights('${escapeHtml(name)}')">
                    <i data-lucide="trending-up"></i> Insights
                </button>
            </div>
        `;
        
        container.appendChild(card);
    });
    
    // Dynamic Lucide rendering
    if (window.lucide) {
        lucide.createIcons();
    }
}

function renderPatientsDashboardOnly() {
    // Only re-render if the Patients tab is currently active
    const patientsTab = document.getElementById("nav-patients");
    if (patientsTab && patientsTab.classList.contains("active")) {
        renderPatientsDashboard();
    }
}

async function fetchPatientCognitiveData(patientName) {
    try {
        const response = await fetch(`/api/analytics/cognitive/${patientName}`);
        const data = await response.json();
        patientCognitiveStatus[patientName] = {
            decline_flag: data.decline_flag,
            trend: data.trend
        };
        renderPatientsDashboardOnly();
    } catch (err) {
        console.error("Error fetching patient cognitive data:", err);
    }
}

function triggerPatientSimCall(patientName) {
    const pReminders = cachedReminders.filter(r => r.patient.toLowerCase().trim() === patientName.toLowerCase().trim());
    if (pReminders.length > 0) {
        triggerSimulatedCall(pReminders[0].id);
    } else {
        triggerSimulatedCall("mock-test");
    }
}

function viewPatientInsights(patientName) {
    // Switch to clinical insights view and set name
    const insightsTab = document.getElementById("nav-insights");
    if (insightsTab) {
        loadInsightsDataForPatient(patientName);
        insightsTab.click();
    }
}

function loadInsightsDataForPatient(patientName) {
    currentInsightsPatient = patientName;
    loadInsightsData();
}

// ==========================================================================
// 10. Sliding Caregiver Notification Drawer Controllers
// ==========================================================================

function triggerAlertDrawer(log) {
    const drawer = document.getElementById("notification-drawer");
    const content = document.getElementById("drawer-content");
    if (!drawer || !content) return;
    
    // Play synthetic chime sound dynamically
    playNotificationSound();
    
    // Determine outcomes and text
    const patient = log.patient || "Patient";
    const medication = log.medication || "Medication";
    const dosage = log.dosage || "";
    const outcome = log.outcome || "ALERT";
    const note = log.guardian_note || log.custom_note || "No additional comments.";
    const isEmergency = outcome === "MEDICAL_EMERGENCY";
    
    // Generate Twilio SMS content
    let smsBody = "";
    if (isEmergency) {
        smsBody = `[CRITICAL EMERGENCY] MedRemind detected a severe crisis for ${patient} during their check-in for ${medication} ${dosage}.\nPatient reported severe distress: '${note}'\nPlease check on them immediately! Call Link: http://127.0.0.1:5000/?action=call&reminder_id=${log.reminder_id || 'test'}`;
    } else {
        let reason_text = "Patient did not successfully take their dose.";
        if (outcome === "REFUSED") reason_text = "Patient actively refused taking the dose.";
        else if (outcome === "CONFUSED") reason_text = "Patient exhibited disorientation or confusion.";
        else if (outcome === "MEDICAL_CONCERN") reason_text = `Patient complained of feeling unwell: '${note}'`;
        else if (outcome === "NO_RESPONSE_FAILED") reason_text = "Patient did not respond to any call attempts today.";
        
        smsBody = `[MedRemind Alert] Call escalation for ${patient} regarding their dose of ${medication} ${dosage}.\nStatus: ${outcome} - ${reason_text}\nPlease coordinate care. Call caregiver dashboard: http://127.0.0.1:5000/?action=call&reminder_id=${log.reminder_id || 'test'}`;
    }
    
    // Format timestamp
    const timeLabel = new Date().toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    
    // Create Alert Notification HTML Element
    const alertCard = document.createElement("div");
    alertCard.className = "drawer-alert-card";
    alertCard.innerHTML = `
        <div class="drawer-alert-title-row">
            <span class="drawer-alert-badge ${isEmergency ? 'badge-emergency' : 'badge-warning'}">${isEmergency ? 'Emergency (Tier 4)' : 'Warning (Tier 3)'}</span>
            <span class="drawer-alert-time">${timeLabel}</span>
        </div>
        
        <div class="drawer-alert-msg-container">
            <span style="font-size:10.2px; font-weight:700; text-transform:uppercase; color:rgba(255,255,255,0.4); display:block; margin-bottom:4px;"><i data-lucide="smartphone" style="width:10px; height:10px; display:inline-block; vertical-align:middle; margin-right:4px;"></i> Mock Twilio SMS Broadcast</span>
            <p class="drawer-alert-msg" style="margin: 0; line-height:1.5; font-size:12.5px;">${escapeHtml(smsBody)}</p>
        </div>
        
        <div class="drawer-alert-actions">
            <button class="btn btn-secondary btn-sm" onclick="closeAlertDrawer(); triggerPatientSimCall('${escapeHtml(patient)}')"><i data-lucide="phone" style="width:12px; height:12px;"></i> Call Now</button>
            <button class="btn btn-primary btn-sm" onclick="closeAlertDrawer(); viewPatientInsights('${escapeHtml(patient)}')"><i data-lucide="trending-up" style="width:12px; height:12px;"></i> Stats</button>
        </div>
    `;
    
    // Prepend to content container
    content.insertBefore(alertCard, content.firstChild);
    
    // Open the drawer
    drawer.classList.add("active");
    
    // Bind close button dynamically inside drawer
    const closeBtn = document.getElementById("btn-close-drawer");
    if (closeBtn) closeBtn.onclick = closeAlertDrawer;
    
    // Auto-create icons
    if (window.lucide) {
        lucide.createIcons();
    }
}

function closeAlertDrawer() {
    const drawer = document.getElementById("notification-drawer");
    if (drawer) drawer.classList.remove("active");
}

function playNotificationSound() {
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        
        // Double electronic chime (standard emergency pager ring)
        const osc1 = audioCtx.createOscillator();
        const gain1 = audioCtx.createGain();
        osc1.connect(gain1);
        gain1.connect(audioCtx.destination);
        osc1.type = 'sine';
        osc1.frequency.setValueAtTime(587.33, audioCtx.currentTime); // D5
        gain1.gain.setValueAtTime(0.25, audioCtx.currentTime);
        gain1.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.3);
        osc1.start(audioCtx.currentTime);
        osc1.stop(audioCtx.currentTime + 0.35);
        
        const osc2 = audioCtx.createOscillator();
        const gain2 = audioCtx.createGain();
        osc2.connect(gain2);
        gain2.connect(audioCtx.destination);
        osc2.type = 'sine';
        osc2.frequency.setValueAtTime(783.99, audioCtx.currentTime + 0.1); // G5
        gain2.gain.setValueAtTime(0.3, audioCtx.currentTime + 0.1);
        gain2.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.4);
        osc2.start(audioCtx.currentTime + 0.1);
        osc2.stop(audioCtx.currentTime + 0.45);
    } catch(e) {
        console.warn("Web Audio API blocked or not supported:", e);
    }
}



