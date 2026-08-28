/* ============================================================
   MediLyft Hub — app.js
   Full rewrite with: processing overlay, stats bar, urgency dial,
   ICD codes, findings tags, follow-up actions, toast notifications
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {

    // ─── DOM References ─────────────────────────────────────────
    const dropZone          = document.getElementById('dropZone');
    const fileInput         = document.getElementById('fileInput');
    const analyzeBtn        = document.getElementById('analyzeBtn');
    const uploadQueue       = document.getElementById('uploadQueue');
    const pdfContainer      = document.getElementById('pdfContainer');
    const patientGrid       = document.getElementById('patientGrid');
    const emptyGridState    = document.getElementById('emptyGridState');
    const processingOverlay = document.getElementById('processingOverlay');

    // ─── State ──────────────────────────────────────────────────
    let currentFiles  = [];
    let patientHistory = [];

    // Fetch history on load
    fetchPatientHistory();

    // ─── DRAG & DROP ─────────────────────────────────────────────
    dropZone.addEventListener('dragover',  e => { e.preventDefault(); dropZone.classList.add('dragover'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    dropZone.addEventListener('drop', e => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });
    dropZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', e => handleFiles(e.target.files));

    function handleFiles(files) {
        currentFiles = Array.from(files);
        uploadQueue.innerHTML = '';
        currentFiles.forEach(file => {
            const item = document.createElement('div');
            item.className = 'queue-item';
            item.innerHTML = `
                <div class="file-info">
                    <strong>${file.name}</strong>
                    <span style="color:var(--text-muted); margin-left:0.5rem;">(${(file.size / 1024 / 1024).toFixed(2)} MB)</span>
                </div>
                <div class="file-status">Ready</div>`;
            uploadQueue.appendChild(item);
        });
        if (currentFiles.length > 0) analyzeBtn.classList.remove('hidden');
    }

    // ─── ANALYZE BUTTON ──────────────────────────────────────────
    analyzeBtn.addEventListener('click', async () => {
        if (!currentFiles.length) return;

        showProcessingOverlay();

        const formData = new FormData();
        currentFiles.forEach(f => formData.append('files', f));

        try {
            const response = await fetch('/api/analyze', { method: 'POST', body: formData });
            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.detail || `HTTP ${response.status}`);
            }
            const result = await response.json();

            if (result.status === 'success') {
                advanceProcessingStep(4); // Step 4: Building dashboard
                await sleep(600);

                const fileURL = URL.createObjectURL(currentFiles[0]);
                const newData = { ...result.data, id: Date.now().toString(), fileUrl: fileURL };
                
                // Remove duplicates if any
                patientHistory = patientHistory.filter(p => p._id !== newData._id);
                patientHistory.unshift(newData);

                hideProcessingOverlay();
                currentFiles = [];
                uploadQueue.innerHTML = '';
                analyzeBtn.classList.add('hidden');

                renderGridDashboard();
                showView('gridDashboardView');
                showToast('success', '✅ Intelligence extracted successfully');
            } else {
                throw new Error(result.detail || 'Unknown AI error');
            }
        } catch (error) {
            hideProcessingOverlay();
            showToast('error', error.message);
        } finally {
            analyzeBtn.disabled = false;
            analyzeBtn.innerHTML = 'Generate Intelligence';
        }
    });

    // ─── PROCESSING OVERLAY ──────────────────────────────────────
    let processingTimer = null;

    function showProcessingOverlay() {
        analyzeBtn.disabled = true;
        processingOverlay.classList.add('active');

        // Reset steps
        [1,2,3,4].forEach(i => {
            const s = document.getElementById(`step${i}`);
            s.classList.remove('active', 'done');
        });
        document.getElementById('ringFill').style.strokeDashoffset = 283;

        // Animate through steps with realistic timing
        advanceProcessingStep(1);
        processingTimer = setTimeout(() => advanceProcessingStep(2), 2500);
        processingTimer = setTimeout(() => advanceProcessingStep(3), 6000);
    }

    function advanceProcessingStep(step) {
        // Mark previous steps as done
        for (let i = 1; i < step; i++) {
            const s = document.getElementById(`step${i}`);
            s.classList.remove('active');
            s.classList.add('done');
            s.querySelector('.step-icon').textContent = '✓';
        }
        // Mark current step active
        const current = document.getElementById(`step${step}`);
        if (current) {
            current.classList.add('active');
        }

        // Advance ring
        const fill = document.getElementById('ringFill');
        const progress = step / 4; // 0.25, 0.5, 0.75, 1.0
        fill.style.strokeDashoffset = 283 * (1 - progress);
    }

    function hideProcessingOverlay() {
        clearTimeout(processingTimer);
        processingOverlay.classList.remove('active');
    }

    // ─── TOAST NOTIFICATIONS ─────────────────────────────────────
    function showToast(type, message) {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 4000);
    }

    // ─── GRID DASHBOARD ──────────────────────────────────────────
    function renderGridDashboard() {
        // Clear existing cards (keep empty state)
        Array.from(patientGrid.querySelectorAll('.grid-card')).forEach(c => c.remove());

        if (!patientHistory.length) {
            emptyGridState.style.display = 'flex';
            updateStats();
            return;
        }

        emptyGridState.style.display = 'none';
        updateStats();

        patientHistory.forEach(patient => {
            const highestRisk = getHighestRisk(patient);
            const urgencyScore = patient.urgency_level ? patient.urgency_level.score : 0;
            const urgencyColor = urgencyScore >= 8 ? 'var(--risk-high)'
                               : urgencyScore >= 5 ? 'var(--risk-med)'
                               : 'var(--risk-low)';
            const urgencyBarWidth = (urgencyScore / 10) * 100;

            const card = document.createElement('div');
            card.className = 'grid-card';
            card.innerHTML = `
                <div class="card-top">
                    <div class="card-patient">
                        <h3>${patient.patient_info.name}</h3>
                        <p>ID: ${patient.patient_info.id || 'N/A'} &bull; DOB: ${patient.patient_info.dob}</p>
                    </div>
                    <div class="card-risk-dot ${highestRisk}" title="Risk level: ${highestRisk}"></div>
                </div>
                <span class="card-doc-type">📄 ${patient.document_type ? patient.document_type.type : 'Clinical Document'}</span>
                <p class="card-summary">${patient.summary ? patient.summary.text : 'No summary available.'}</p>
                <div class="card-urgency">
                    <span style="color:var(--text-muted); font-size:0.72rem;">Urgency</span>
                    <div class="urgency-bar-bg">
                        <div class="urgency-bar-fill" style="width:${urgencyBarWidth}%; background:${urgencyColor};"></div>
                    </div>
                    <span style="color:${urgencyColor}; font-weight:700; font-size:0.78rem;">${urgencyScore}/10</span>
                </div>
                <div class="card-footer">
                    <span>${patient.medications ? patient.medications.length : 0} meds &bull; ${patient.risk_flags ? patient.risk_flags.length : 0} risks</span>
                    <span>Conf: <span class="card-conf-badge">${patient.summary ? patient.summary.confidence_score : '—'}%</span></span>
                </div>`;

            card.addEventListener('click', () => openPatientDetail(patient));
            patientGrid.appendChild(card);
        });

        updateSidebarList();
    }

    function getHighestRisk(patient) {
        if (!patient.risk_flags || !patient.risk_flags.length) return 'low';
        if (patient.risk_flags.some(r => r.level.toLowerCase() === 'high'))   return 'high';
        if (patient.risk_flags.some(r => r.level.toLowerCase() === 'medium')) return 'medium';
        return 'low';
    }

    function updateStats() {
        document.getElementById('statTotal').textContent    = patientHistory.length;
        document.getElementById('statHighRisk').textContent = patientHistory.filter(p => getHighestRisk(p) === 'high').length;
        const totalMeds = patientHistory.reduce((acc, p) => acc + (p.medications ? p.medications.length : 0), 0);
        document.getElementById('statTotalMeds').textContent = totalMeds;
        if (patientHistory.length) {
            const avgConf = Math.round(patientHistory.reduce((acc, p) => acc + (p.summary ? p.summary.confidence_score : 0), 0) / patientHistory.length);
            document.getElementById('statAvgConf').textContent = avgConf + '%';
        } else {
            document.getElementById('statAvgConf').textContent = '—';
        }
    }

    // ─── PATIENT DETAIL VIEW ─────────────────────────────────────
    function openPatientDetail(data) {
        // PDF Viewer
        if (data.file_id) {
            // Document retrieved securely from MongoDB GridFS
            pdfContainer.innerHTML = `<iframe src="http://127.0.0.1:8000/api/documents/${data.file_id}#toolbar=0&view=FitH" type="application/pdf" width="100%" height="100%" style="border:none;"></iframe>`;
        } else if (data.fileUrl) {
            // Temporary fallback for older unsaved sessions
            pdfContainer.innerHTML = `<iframe src="${data.fileUrl}#toolbar=0&view=FitH" type="application/pdf" width="100%" height="100%" style="border:none;"></iframe>`;
        } else {
            pdfContainer.innerHTML = `<div style="display:flex; height:100%; align-items:center; justify-content:center; color:var(--text-muted); flex-direction:column; gap:1rem;">
                <span style="font-size:3rem;">📂</span>
                <p>Source document not stored in database.</p>
            </div>`;
        }

        // Document Type Badge
        const badge = document.getElementById('docTypeBadge');
        badge.innerHTML = data.document_type
            ? `📄 ${data.document_type.type} <span style="opacity:0.7; font-size:0.72rem; margin-left:0.4rem;">${data.document_type.confidence_score}% Conf</span>`
            : '📄 Clinical Document';

        // Patient Overview
        const pi = data.patient_info;
        document.getElementById('patientConfPill').textContent = `${pi.confidence_score || '—'}% Conf`;
        document.getElementById('patientDetails').innerHTML = `
            <div class="detail-field"><label>Full Name</label>
                <p>${pi.name || 'N/A'}</p>
            </div>
            <div class="detail-field"><label>Patient ID</label><p>${pi.id || 'N/A'}</p></div>
            <div class="detail-field"><label>Date of Birth</label><p>${pi.dob || 'N/A'}</p></div>
            <div class="detail-field"><label>Info Confidence</label><p style="color:var(--accent-green)">${pi.confidence_score || '—'}%</p></div>`;

        // Urgency Dial
        renderUrgencyDial(data.urgency_level);

        // Clinical Summary
        document.getElementById('summaryConfPill').textContent = `${data.summary ? data.summary.confidence_score : '—'}% Conf`;
        document.getElementById('clinicalSummary').textContent = data.summary ? data.summary.text : 'No summary available.';

        // Risk Flags
        renderRiskFlags(data.risk_flags);

        // Medications
        renderMedications(data.medications);

        // Clinical Findings
        renderFindings(data.clinical_findings);

        // ICD Codes
        renderIcdCodes(data.icd_codes);

        // Follow-up Actions
        renderFollowups(data.follow_up_actions);
        
        showView('dashboardView');
    }

    function renderUrgencyDial(urgency) {
        const score = urgency ? urgency.score : 0;
        const label = urgency ? urgency.label : '—';
        const conf  = urgency ? urgency.confidence_score : '—';

        document.getElementById('dialScore').textContent   = score;
        document.getElementById('urgencyLabel').textContent = label;
        document.getElementById('urgencyConfPill').textContent = `${conf}% Conf`;

        const descMap = {
            'Critical': 'Immediate clinical intervention required.',
            'High':     'Elevated risk — prioritize follow-up actions.',
            'Moderate': 'Monitor closely, follow standard care protocols.',
            'Low':      'Routine care, no immediate concerns identified.'
        };
        document.getElementById('urgencyDesc').textContent = descMap[label] || 'Urgency level assessed from document.';

        // Color based on score
        const color = score >= 8 ? 'var(--risk-high)' : score >= 5 ? 'var(--risk-med)' : 'var(--risk-low)';
        document.getElementById('dialScore').style.color = color;

        // Animate dial: circumference = 2π × 32 ≈ 201
        const circumference = 201;
        const offset = circumference - (score / 10) * circumference;
        const fill = document.getElementById('dialFill');
        fill.style.stroke = color;
        // Trigger animation after brief delay
        setTimeout(() => { fill.style.strokeDashoffset = offset; }, 100);
        fill.style.strokeDashoffset = circumference; // reset first
    }

    function renderRiskFlags(flags) {
        const list = document.getElementById('riskList');
        list.innerHTML = '';
        if (!flags || !flags.length) {
            list.innerHTML = '<li style="color:var(--text-muted); font-size:0.875rem;">No significant risks identified.</li>';
            return;
        }
        flags.forEach(risk => {
            const li = document.createElement('li');
            li.className = `risk-item ${risk.level.toLowerCase()}`;
            li.innerHTML = `
                <span class="risk-level-tag">${risk.level}</span>
                <div style="flex:1">
                    <div>${risk.reason}</div>
                    <div class="risk-conf">${risk.confidence_score}% confidence</div>
                </div>`;
            list.appendChild(li);
        });
    }

    function renderMedications(meds) {
        const list = document.getElementById('medList');
        list.innerHTML = '';
        if (!meds || !meds.length) {
            list.innerHTML = '<li style="color:var(--text-muted); font-size:0.875rem;">No medications listed.</li>';
            return;
        }
        meds.forEach(med => {
            const li = document.createElement('li');
            li.className = 'med-item';
            const statusClass = (med.status || '').toLowerCase().replace(/ /g, '-');
            li.innerHTML = `
                <div style="flex:1">
                    <div class="med-name">${med.name}</div>
                    <div class="med-conf">${med.confidence_score}% confidence</div>
                </div>
                <span class="med-status-badge ${statusClass}">${med.status}</span>`;
            list.appendChild(li);
        });
    }

    function renderFindings(findings) {
        const cloud = document.getElementById('findingsTags');
        cloud.innerHTML = '';
        if (!findings || !findings.length) {
            cloud.innerHTML = '<span style="color:var(--text-muted); font-size:0.875rem;">No clinical findings extracted.</span>';
            return;
        }
        findings.forEach(f => {
            const tag = document.createElement('span');
            tag.className = 'finding-tag';
            const confColor = f.confidence_score >= 90 ? 'var(--risk-low)'
                            : f.confidence_score >= 70 ? 'var(--risk-med)'
                            : 'var(--risk-high)';
            tag.innerHTML = `
                <span class="finding-conf-dot" style="background:${confColor};" title="${f.confidence_score}% confidence"></span>
                ${f.finding}`;
            cloud.appendChild(tag);
        });
    }

    function renderIcdCodes(codes) {
        const list = document.getElementById('icdList');
        list.innerHTML = '';
        if (!codes || !codes.length) {
            list.innerHTML = '<li style="color:var(--text-muted); font-size:0.875rem;">No ICD-10 codes extracted.</li>';
            return;
        }
        codes.forEach(c => {
            const li = document.createElement('li');
            li.className = 'icd-item';
            li.innerHTML = `
                <span class="icd-code">${c.code}</span>
                <span class="icd-desc">${c.description}</span>
                <span class="icd-conf">${c.confidence_score}%</span>`;
            list.appendChild(li);
        });
    }

    function renderFollowups(actions) {
        const list = document.getElementById('followupList');
        list.innerHTML = '';
        if (!actions || !actions.length) {
            list.innerHTML = '<li style="color:var(--text-muted); font-size:0.875rem;">No follow-up actions extracted.</li>';
            return;
        }
        actions.forEach(a => {
            const li = document.createElement('li');
            li.className = 'followup-item';
            const pClass = (a.priority || 'routine').toLowerCase();
            li.innerHTML = `
                <span class="followup-priority ${pClass}">${a.priority}</span>
                <span class="followup-text">${a.action}</span>`;
            list.appendChild(li);
        });
    }

    function updateSidebarList() {
        const list = document.getElementById('patientList');
        list.innerHTML = '';
        if (patientHistory.length === 0) {
            list.innerHTML = '<li style="color:var(--text-muted);">No patients yet</li>';
            return;
        }

        patientHistory.forEach((patient) => {
            const pi = patient.patient_info || {};
            const dt = patient.document_type || {};
            
            const li = document.createElement('li');
            li.innerHTML = `
                <div style="font-weight:600; color:var(--text-primary); margin-bottom:0.2rem;">${pi.name || 'Unknown Patient'}</div>
                <div style="font-size:0.85rem;">${dt.type || 'Clinical Doc'}</div>
            `;
            li.addEventListener('click', () => {
                openPatientDetail(patient);
            });
            list.appendChild(li);
        });
    }

    async function fetchPatientHistory() {
        try {
            const response = await fetch('http://127.0.0.1:8000/api/patients');
            if (response.ok) {
                const result = await response.json();
                if (result.status === 'success') {
                    // Only keep records that aren't already in patientHistory (preserve local fileUrl objects)
                    const fetched = result.data || [];
                    const localIds = patientHistory.map(p => p._id);
                    const newHistorical = fetched.filter(f => !localIds.includes(f._id));
                    patientHistory = [...patientHistory, ...newHistorical];
                    
                    updateSidebarList();
                    renderGridDashboard();
                }
            }
        } catch (error) {
            console.error("Failed to fetch patient history:", error);
        }
    }

    // ─── VIEW ROUTING ─────────────────────────────────────────────
    window.showView = function(viewId) {
        document.querySelectorAll('.view').forEach(v => {
            v.classList.remove('active');
        });
        const target = document.getElementById(viewId);
        target.classList.remove('hidden');

        // Trigger active after next frame for transition
        requestAnimationFrame(() => {
            requestAnimationFrame(() => target.classList.add('active'));
        });

        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        if (viewId === 'gridDashboardView') {
            document.getElementById('navDashboard').classList.add('active');
            renderGridDashboard();
        }
    };

    window.startNewSession = function() {
        showView('uploadView');
        uploadQueue.innerHTML = '';
        fileInput.value = '';
        currentFiles = [];
        analyzeBtn.classList.add('hidden');
    };

    // ─── HELPERS ─────────────────────────────────────────────────
    function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

    // ─── INIT ─────────────────────────────────────────────────────
    renderGridDashboard();
});
