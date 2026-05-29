/* ==========================================================================
   MedRemind Caregiver Portal client JS Controller
   Logic: REST API Client, Metrics, SPA Tab Switcher, & Stateful Call Simulator
   ========================================================================== */

document.addEventListener("DOMContentLoaded", () => {
    // Initialize Dashboard UI Elements
    initModalControls();
    initTabSwitcher();
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

function loadDashboardData() {
    loadReminders();
    loadLogs();
}

async function loadReminders() {
    const tbody = document.getElementById("reminders-tbody");
    const boardTbody = document.getElementById("schedule-board-tbody");
    
    try {
        const response = await fetch("/api/reminders");
        const reminders = await response.json();
        cachedReminders = reminders;
        
        // Update metric counts
        document.getElementById("metric-reminders").innerText = reminders.length;
        
        // 1. Render Dashboard Table Preview
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
        
        // 2. Render Full-width Scheduler Board View
        renderScheduleBoard(reminders);
        
        // Dynamic Lucide rendering
        if (window.lucide) {
            lucide.createIcons();
        }
        
    } catch (err) {
        console.error("Error fetching reminders schedule:", err);
        tbody.innerHTML = `<tr><td colspan="6" class="table-empty text-red">Failed to load schedule.</td></tr>`;
    }
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
        
        // Update statistical Metrics cards
        const m = data.metrics;
        document.getElementById("metric-calls").innerText = m.total_calls;
        document.getElementById("metric-adherence").innerText = m.adherence_rate;
        
        // Highlight adherence score color based on performance thresholds
        const adherenceCard = document.getElementById("metric-adherence-card");
        adherenceCard.className = "stat-card";
        if (m.adherence_rate >= 80) adherenceCard.classList.add("card-glow-green");
        else if (m.adherence_rate >= 50) adherenceCard.classList.add("card-glow-blue");
        else adherenceCard.classList.add("card-glow-amber");
        
        // Compile alerts (Medical concerns, failures, or refusals)
        let alertCount = 0;
        const feedCount = document.getElementById("feed-count");
        feedCount.innerText = `${data.logs.length} Sessions`;
        
        // 1. Render Dashboard Live Feed Preview
        if (data.logs.length === 0) {
            logsFeed.innerHTML = `<div class="feed-empty">No activity logs recorded yet.</div>`;
            document.getElementById("metric-alerts").innerText = 0;
            if (logsTbody) {
                logsTbody.innerHTML = `<tr><td colspan="6" class="table-empty">No call logs recorded.</td></tr>`;
            }
            return;
        }
        
        logsFeed.innerHTML = "";
        const previewLogs = data.logs.slice(0, 5); // Show latest 5 on dashboard feed
        previewLogs.forEach(log => {
            const out = log.outcome;
            const isAlert = ["MEDICAL_CONCERN", "REFUSED", "CONFUSED", "NO_RESPONSE_FAILED"].includes(out);
            if (isAlert) alertCount++;
            
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
        
        // Compile full list for total metrics
        let totalAlerts = 0;
        data.logs.forEach(l => {
            if (["MEDICAL_CONCERN", "REFUSED", "CONFUSED", "NO_RESPONSE_FAILED"].includes(l.outcome)) {
                totalAlerts++;
            }
        });
        document.getElementById("metric-alerts").innerText = totalAlerts;
        
        // 2. Render Full-width Audit Log View
        renderLogsBoard(data.logs);
        
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
                            <p style="font-size: 13.5px; line-height: 1.6;"><strong>Outcome:</strong> <span class="badge-outcome ${badgeClass}">${out.replace("_", " ")}</span></p>
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
        { id: "nav-reminders", viewId: "view-schedule", title: "Medication Scheduler", subtitle: "Manage active schedules, patient details, and background reminder alerts" },
        { id: "nav-activity", viewId: "view-activity", title: "Audit Log Database", subtitle: "Review call outcomes, detailed transcripts, and historical adherence tracking" }
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
