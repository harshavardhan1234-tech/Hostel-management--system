// App Frontend Interactions, WebRTC Biometrics & Dynamic Helpers

// Toast Notification Manager
function showToast(message, type = 'success') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast-msg ${type}`;
  
  const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : '⚠️';
  toast.innerHTML = `<span style="font-size: 1.2rem;">${icon}</span><span>${message}</span>`;
  
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Camera Utility Class
class BiometricCamera {
  constructor(videoElementId, canvasOverlayId) {
    this.video = document.getElementById(videoElementId);
    this.overlay = document.getElementById(canvasOverlayId);
    this.stream = null;
    this.isScanning = false;
    this.scanInterval = null;
  }

  async start() {
    if (!this.video) return false;
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }
      });
      this.video.srcObject = this.stream;
      await this.video.play();
      return true;
    } catch (err) {
      console.error('Webcam Access Error:', err);
      showToast('Camera access denied or unavailable: ' + err.message, 'error');
      return false;
    }
  }

  stop() {
    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
      this.stream = null;
    }
    if (this.scanInterval) {
      clearInterval(this.scanInterval);
      this.scanInterval = null;
    }
    this.isScanning = false;
  }

  captureFrameAsBase64() {
    if (!this.video || !this.video.videoWidth) return null;
    const canvas = document.createElement('canvas');
    canvas.width = this.video.videoWidth;
    canvas.height = this.video.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(this.video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', 0.85);
  }

  drawBoundingBox(box, label, color = '#10b981') {
    if (!this.overlay || !box) return;
    const ctx = this.overlay.getContext('2d');
    this.overlay.width = this.video.clientWidth;
    this.overlay.height = this.video.clientHeight;
    
    ctx.clearRect(0, 0, this.overlay.width, this.overlay.height);

    const scaleX = this.overlay.width / this.video.videoWidth;
    const scaleY = this.overlay.height / this.video.videoHeight;

    const [x, y, w, h] = box;
    const drawX = x * scaleX;
    const drawY = y * scaleY;
    const drawW = w * scaleX;
    const drawH = h * scaleY;

    // Draw box
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.strokeRect(drawX, drawY, drawW, drawH);

    // Label tag
    if (label) {
      ctx.fillStyle = color;
      ctx.fillRect(drawX, drawY - 26, Math.max(drawW, 140), 24);
      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 12px Plus Jakarta Sans, sans-serif';
      ctx.fillText(label, drawX + 6, drawY - 9);
    }
  }

  clearOverlay() {
    if (!this.overlay) return;
    const ctx = this.overlay.getContext('2d');
    ctx.clearRect(0, 0, this.overlay.width, this.overlay.height);
  }
}

// Student Registration Multi-Sample Face Capture
let enrollCamera = null;
let capturedSamples = [];
const TOTAL_SAMPLES_NEEDED = 10;

async function initEnrollmentCamera() {
  enrollCamera = new BiometricCamera('enroll-video', 'enroll-overlay');
  const started = await enrollCamera.start();
  if (started) {
    document.getElementById('start-cam-btn').style.display = 'none';
    document.getElementById('capture-progress-area').style.display = 'block';
    startAutoCaptureLoop();
  }
}

function startAutoCaptureLoop() {
  capturedSamples = [];
  const progressBar = document.getElementById('enroll-progress-bar');
  const progressText = document.getElementById('enroll-progress-text');
  
  const interval = setInterval(() => {
    if (capturedSamples.length >= TOTAL_SAMPLES_NEEDED) {
      clearInterval(interval);
      progressText.innerText = "Captured 10/10 Samples! Ready for registration.";
      showToast("All biometric samples captured successfully!", "success");
      document.getElementById('enroll-complete-badge').style.display = 'inline-flex';
      document.getElementById('face-samples-input').value = JSON.stringify(capturedSamples);
      return;
    }

    const frame = enrollCamera.captureFrameAsBase64();
    if (frame) {
      capturedSamples.push(frame);
      const pct = Math.round((capturedSamples.length / TOTAL_SAMPLES_NEEDED) * 100);
      if (progressBar) progressBar.style.width = `${pct}%`;
      if (progressText) progressText.innerText = `Captured ${capturedSamples.length}/${TOTAL_SAMPLES_NEEDED} samples (${pct}%)`;
    }
  }, 350);
}

// Leave Application Auto Date Calculator
function setupLeaveFormCalculations() {
  const leaveDt = document.getElementById('leave_dt');
  const returnDt = document.getElementById('return_dt');
  const totalDays = document.getElementById('total_days');

  if (!leaveDt || !returnDt || !totalDays) return;

  function calc() {
    if (leaveDt.value && returnDt.value) {
      const d1 = new Date(leaveDt.value);
      const d2 = new Date(returnDt.value);
      const diffTime = d2 - d1;
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)) + 1;
      totalDays.value = diffDays > 0 ? diffDays : 1;
    }
  }

  leaveDt.addEventListener('change', calc);
  returnDt.addEventListener('change', calc);
}

// Gate Biometric Verification Scanner
let gateCamera = null;
let scanBusy = false;

async function initGateScanner() {
  gateCamera = new BiometricCamera('gate-video', 'gate-overlay');
  const started = await gateCamera.start();
  if (!started) return;

  document.getElementById('gate-scanner-status').innerText = "Scanning for faces...";
  
  // Continuous scanning loop
  gateCamera.scanInterval = setInterval(async () => {
    if (scanBusy) return;
    const frame = gateCamera.captureFrameAsBase64();
    if (!frame) return;

    scanBusy = true;
    try {
      const resp = await fetch('/api/face/verify-gate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image: frame })
      });
      const data = await resp.json();

      if (data.found && data.student) {
        const student = data.student;
        const leave = data.leave;
        const isAuthorized = data.is_authorized;

        const color = isAuthorized ? '#10b981' : '#f59e0b';
        gateCamera.drawBoundingBox(data.box, `${student.first_name} (${data.confidence}%)`, color);

        // Populate match details card
        document.getElementById('match-card').style.display = 'block';
        document.getElementById('student-name').innerText = `${student.first_name} ${student.last_name}`;
        document.getElementById('student-prn').innerText = student.prn;
        document.getElementById('student-room').innerText = `${student.hostel_name} - ${student.room_number}`;
        document.getElementById('student-branch').innerText = `${student.branch} (${student.year})`;
        document.getElementById('match-confidence').innerText = `${data.confidence}% Match`;
        
        const leaveStatusBadge = document.getElementById('leave-status-badge');
        if (leave && leave.status === 'Approved') {
          leaveStatusBadge.className = 'badge badge-approved';
          leaveStatusBadge.innerHTML = `<span class="badge-dot"></span> Approved Leave (${leave.leave_type})`;
          document.getElementById('leave-reason').innerText = `Reason: ${leave.reason} (Valid: ${leave.leaving_date} to ${leave.return_date})`;
        } else {
          leaveStatusBadge.className = 'badge badge-rejected';
          leaveStatusBadge.innerHTML = `<span class="badge-dot"></span> No Active Approved Leave`;
          document.getElementById('leave-reason').innerText = `Student has no approved leave on record today.`;
        }

        // Configure Action buttons
        document.getElementById('btn-log-exit').onclick = () => logGateAction(student.id, leave ? leave.id : null, 'OUT', isAuthorized, data.confidence);
        document.getElementById('btn-log-entry').onclick = () => logGateAction(student.id, leave ? leave.id : null, 'IN', true, data.confidence);

      } else {
        if (data.box) {
          gateCamera.drawBoundingBox(data.box, 'Unknown', '#f43f5e');
        } else {
          gateCamera.clearOverlay();
        }
        document.getElementById('gate-scanner-status').innerText = data.message || "Searching for face...";
      }
    } catch (e) {
      console.error('Scan error:', e);
    } finally {
      scanBusy = false;
    }
  }, 700);
}

async function logGateAction(studentId, leaveId, movementType, authorized, confidence) {
  try {
    const resp = await fetch('/api/gate/log-movement', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        student_id: studentId,
        leave_id: leaveId,
        movement_type: movementType,
        authorized: authorized,
        confidence: confidence
      })
    });
    const result = await resp.json();
    if (result.status === 'success') {
      showToast(`Gate ${movementType} logged! Parent SMS & Email dispatched.`, 'success');
      setTimeout(() => location.reload(), 1500);
    } else {
      showToast(result.message, 'error');
    }
  } catch (err) {
    showToast('Failed to log gate movement: ' + err.message, 'error');
  }
}

// Leave Request Status Action (Approve / Reject)
async function updateLeaveStatus(requestId, newStatus) {
  let reason = '';
  if (newStatus === 'Rejected') {
    reason = prompt('Enter rejection reason for student and parents:', 'Administrative policy');
    if (reason === null) return;
  }

  try {
    const resp = await fetch(`/api/leave/update-status/${requestId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus, rejection_reason: reason })
    });
    const res = await resp.json();
    if (res.status === 'success') {
      showToast(`Leave request ${newStatus} successfully!`, 'success');
      setTimeout(() => location.reload(), 1200);
    } else {
      showToast(res.message, 'error');
    }
  } catch (e) {
    showToast('Error updating status: ' + e.message, 'error');
  }
}

// Table Search & Filter Helper
function setupTableSearch(inputId, tableId) {
  const input = document.getElementById(inputId);
  const table = document.getElementById(tableId);
  if (!input || !table) return;

  input.addEventListener('keyup', () => {
    const query = input.value.toLowerCase();
    const rows = table.getElementsByTagName('tbody')[0].getElementsByTagName('tr');
    for (let row of rows) {
      const text = row.innerText.toLowerCase();
      row.style.display = text.includes(query) ? '' : 'none';
    }
  });
}

// Export Table to CSV
function exportTableToCSV(tableId, filename = 'export.csv') {
  const table = document.getElementById(tableId);
  if (!table) return;
  
  let csv = [];
  const rows = table.querySelectorAll('tr');
  for (let row of rows) {
    if (row.style.display === 'none') continue;
    const cols = row.querySelectorAll('th, td');
    const rowData = [];
    for (let col of cols) {
      rowData.push(`"${col.innerText.replace(/"/g, '""').trim()}"`);
    }
    csv.push(rowData.join(','));
  }

  const blob = new Blob([csv.join('\n')], { type: 'text/csv' });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.setAttribute('href', url);
  a.setAttribute('download', filename);
  a.click();
}

document.addEventListener('DOMContentLoaded', () => {
  setupLeaveFormCalculations();
  setupTableSearch('search-input', 'data-table');
});
