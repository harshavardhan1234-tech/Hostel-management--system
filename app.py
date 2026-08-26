import os
import json
from functools import wraps
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

import database
import face_utils
import mail_utils

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "hostel_biometric_portal_secret_key_2026")

# Initialize database schema on start
database.init_db()

@app.context_processor
def inject_global_data():
    """Provides gate status and current user details to all templates"""
    is_allowed, time_str, message = face_utils.check_gate_time_status()
    current_student = None
    if session.get('user_id') and session.get('role') == 'student':
        conn = database.get_db_connection()
        current_student = conn.execute("SELECT * FROM students WHERE user_id = ?", (session['user_id'],)).fetchone()
        conn.close()

    return {
        'gate_status': {
            'is_allowed': is_allowed,
            'time_str': time_str,
            'message': message
        },
        'today_str': date.today().strftime('%Y-%m-%d'),
        'current_student': current_student
    }

# ==================== ACCESS CONTROL DECORATORS ====================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please sign in to access this page.", "warning")
            return redirect(url_for('login_choice'))
        return f(*args, **kwargs)
    return decorated_function

def warden_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in as Warden/Admin to access this section.", "warning")
            return redirect(url_for('login_warden'))
        if session.get('role') not in ['warden', 'admin']:
            flash("Access Restricted: Only Wardens and Administrators can view the staff portal.", "error")
            return redirect(url_for('student_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in with your Student account to access this page.", "warning")
            return redirect(url_for('login_student'))
        return f(*args, **kwargs)
    return decorated_function

# ==================== HOME & AUTH ROUTES ====================

@app.route('/')
def index():
    conn = database.get_db_connection()
    total_students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    pending_leaves = conn.execute("SELECT COUNT(*) FROM leave_requests WHERE status = 'Pending'").fetchone()[0]
    approved_leaves = conn.execute("SELECT COUNT(*) FROM leave_requests WHERE status = 'Approved'").fetchone()[0]
    today_movements = conn.execute("SELECT COUNT(*) FROM movement_logs WHERE date(timestamp) = date('now')").fetchone()[0]
    enrolled_faces = conn.execute("SELECT COUNT(*) FROM students WHERE face_enrolled = 1").fetchone()[0]
    conn.close()

    stats = {
        'total_students': total_students,
        'pending_leaves': pending_leaves,
        'approved_leaves': approved_leaves,
        'today_movements': today_movements,
        'enrolled_faces': enrolled_faces
    }
    return render_template('index.html', stats=stats)

@app.route('/login')
def login_choice():
    """Separate role selection page"""
    if 'user_id' in session:
        if session.get('role') in ['warden', 'admin']:
            return redirect(url_for('portal_dashboard'))
        return redirect(url_for('student_dashboard'))
    return render_template('login_choice.html')

@app.route('/login/student', methods=['GET', 'POST'])
def login_student():
    """Dedicated Student Login Portal"""
    if 'user_id' in session and session.get('role') == 'student':
        return redirect(url_for('student_dashboard'))

    if request.method == 'POST':
        prn = request.form.get('prn', '').strip().upper()
        password = request.form.get('password', '').strip()

        conn = database.get_db_connection()
        student = conn.execute("SELECT * FROM students WHERE prn = ?", (prn,)).fetchone()
        
        user = None
        if student and student['user_id']:
            user = conn.execute("SELECT * FROM users WHERE id = ?", (student['user_id'],)).fetchone()
        elif not student:
            # Check users table directly in case username was used
            user = conn.execute("SELECT * FROM users WHERE username = ? AND role = 'student'", (prn,)).fetchone()

        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = 'student'
            flash(f"Welcome back, {student['first_name'] if student else user['username']}!", 'success')
            return redirect(url_for('student_dashboard'))
        else:
            flash("Invalid PRN or Password. Please verify your student credentials.", 'error')

    return render_template('login_student.html')

@app.route('/login/warden', methods=['GET', 'POST'])
def login_warden():
    """Dedicated Warden & Admin Login Portal"""
    if 'user_id' in session and session.get('role') in ['warden', 'admin']:
        return redirect(url_for('portal_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        conn = database.get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ? AND role IN ('warden', 'admin')", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash(f"Staff Access Granted: Logged in as {user['role'].capitalize()} ({user['username']})", 'success')
            return redirect(url_for('portal_dashboard'))
        else:
            flash("Invalid Staff Username or Password.", 'error')

    return render_template('login_warden.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been signed out successfully.", 'success')
    return redirect(url_for('index'))

# ==================== STUDENT PRIVATE DASHBOARD ====================

@app.route('/student/dashboard')
@student_required
def student_dashboard():
    """Private Student Portal - Students can ONLY see their own data"""
    conn = database.get_db_connection()
    student = conn.execute("SELECT * FROM students WHERE user_id = ?", (session['user_id'],)).fetchone()
    
    if not student:
        # Fallback if student record linked by username (PRN)
        student = conn.execute("SELECT * FROM students WHERE prn = ?", (session['username'],)).fetchone()

    if not student:
        conn.close()
        flash("Student profile not found. Please contact the warden.", "error")
        return redirect(url_for('index'))

    # Fetch ONLY this student's leave requests
    my_leaves = conn.execute("""
        SELECT * FROM leave_requests
        WHERE student_id = ?
        ORDER BY applied_at DESC
    """, (student['id'],)).fetchall()

    # Fetch ONLY this student's gate movement logs
    my_movements = conn.execute("""
        SELECT * FROM movement_logs
        WHERE student_id = ?
        ORDER BY timestamp DESC
    """, (student['id'],)).fetchall()

    conn.close()
    return render_template(
        'student/dashboard.html',
        student=student,
        leaves=my_leaves,
        movements=my_movements
    )

# ==================== STUDENT REGISTRATION & BIOMETRICS ====================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fname = request.form.get('fname', '').strip()
        mname = request.form.get('mname', '').strip()
        lname = request.form.get('lname', '').strip()
        gender = request.form.get('gender')
        dob = request.form.get('dob')
        prn = request.form.get('prn', '').strip().upper()
        branch = request.form.get('branch')
        year = request.form.get('year')
        hostelname = request.form.get('hostelname', '').strip()
        room = request.form.get('room', '').strip()
        contact = request.form.get('contact', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        parent_name = request.form.get('parent_name', '').strip()
        parent_contact = request.form.get('parent_contact', '').strip()
        parent_email = request.form.get('parent_email', '').strip()
        face_samples_raw = request.form.get('face_samples', '')

        conn = database.get_db_connection()
        existing = conn.execute("SELECT id FROM students WHERE prn = ?", (prn,)).fetchone()
        if existing:
            conn.close()
            flash(f"A student with PRN '{prn}' is already registered!", 'error')
            return redirect(url_for('register'))

        # Create user account
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, email) VALUES (?, ?, 'student', ?)",
            (prn, generate_password_hash(password), email)
        )
        u_id = cursor.lastrowid

        # Insert student record
        cursor.execute("""
            INSERT INTO students (
                user_id, prn, first_name, middle_name, last_name, gender, dob, branch, year,
                hostel_name, room_number, contact, parent_name, parent_contact, parent_email
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            u_id, prn, fname, mname, lname, gender, dob, branch, year,
            hostelname, room, contact, parent_name, parent_contact, parent_email
        ))
        s_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Process face samples if captured
        if face_samples_raw:
            try:
                samples = json.loads(face_samples_raw)
                success, msg = face_utils.save_face_samples(s_id, samples)
                flash(f"Registration successful! Biometric samples enrolled. You can now login with PRN: {prn}", 'success')
            except Exception as e:
                flash(f"Student registered! Biometric setup note: {e}", 'warning')
        else:
            flash(f"Student registered successfully! Please login with your PRN: {prn}", 'success')

        return redirect(url_for('login_student'))

    return render_template('register.html')

# ==================== LEAVE APPLICATION (STUDENT) ====================

@app.route('/leave/apply', methods=['GET', 'POST'])
def leave_apply():
    conn = database.get_db_connection()

    # Determine current student if logged in
    current_student = None
    if session.get('user_id'):
        if session.get('role') == 'student':
            current_student = conn.execute("SELECT * FROM students WHERE user_id = ?", (session['user_id'],)).fetchone()
            if not current_student:
                current_student = conn.execute("SELECT * FROM students WHERE prn = ?", (session['username'],)).fetchone()

    if request.method == 'POST':
        # If student is logged in, force their student_id to prevent applying for others
        if session.get('role') == 'student' and current_student:
            student_id = current_student['id']
        else:
            student_id = request.form.get('student_id')

        leave_type = request.form.get('leave_type')
        leave_dt = request.form.get('leave_dt')
        return_dt = request.form.get('return_dt')
        period = request.form.get('period')
        total_days = request.form.get('total_days', 1)
        reason = request.form.get('reason', '').strip()
        permission_from = request.form.get('permission_from')
        address_during_leave = request.form.get('address_during_leave', '').strip()

        conn.execute("""
            INSERT INTO leave_requests (
                student_id, leave_type, leaving_date, return_date, period, total_days,
                reason, permission_from, address_during_leave, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending')
        """, (
            student_id, leave_type, leave_dt, return_dt, period, total_days,
            reason, permission_from, address_during_leave
        ))
        conn.commit()

        # Send alert to parents about leave application
        student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        if student:
            mail_utils.send_parent_notification(
                f"{student['first_name']} {student['last_name']}",
                student['parent_contact'],
                student['parent_email'],
                'LEAVE_APPLIED',
                f"{leave_type} ({leave_dt} to {return_dt}) - Reason: {reason}"
            )

        conn.close()
        flash("Hostel Leave Application submitted successfully! Awaiting Warden approval.", 'success')
        
        if session.get('role') == 'student':
            return redirect(url_for('student_dashboard'))
        return redirect(url_for('index'))

    # If warden, they can see student selector; if student, restricted to self
    students = []
    if session.get('role') in ['warden', 'admin'] or not session.get('user_id'):
        students = conn.execute("SELECT * FROM students ORDER BY first_name ASC").fetchall()

    conn.close()
    return render_template('leave_apply.html', students=students, current_student=current_student)

# ==================== WARDEN / ADMIN PORTAL (PROTECTED) ====================

@app.route('/portal/dashboard')
@warden_required
def portal_dashboard():
    conn = database.get_db_connection()
    total_students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    pending_leaves = conn.execute("SELECT COUNT(*) FROM leave_requests WHERE status = 'Pending'").fetchone()[0]
    approved_leaves = conn.execute("SELECT COUNT(*) FROM leave_requests WHERE status = 'Approved'").fetchone()[0]
    today_movements = conn.execute("SELECT COUNT(*) FROM movement_logs WHERE date(timestamp) = date('now')").fetchone()[0]
    enrolled_faces = conn.execute("SELECT COUNT(*) FROM students WHERE face_enrolled = 1").fetchone()[0]

    pending_leaves_list = conn.execute("""
        SELECT l.*, s.first_name, s.last_name, s.prn, s.hostel_name, s.room_number
        FROM leave_requests l
        JOIN students s ON l.student_id = s.id
        WHERE l.status = 'Pending'
        ORDER BY l.applied_at DESC
        LIMIT 5
    """).fetchall()

    recent_movements = conn.execute("""
        SELECT m.*, s.first_name, s.last_name, s.prn, s.hostel_name, s.room_number
        FROM movement_logs m
        JOIN students s ON m.student_id = s.id
        ORDER BY m.timestamp DESC
        LIMIT 5
    """).fetchall()

    conn.close()

    stats = {
        'total_students': total_students,
        'pending_leaves': pending_leaves,
        'approved_leaves': approved_leaves,
        'today_movements': today_movements,
        'enrolled_faces': enrolled_faces
    }

    return render_template(
        'portal/dashboard.html',
        stats=stats,
        pending_leaves_list=pending_leaves_list,
        recent_movements=recent_movements
    )

@app.route('/portal/verify-leave')
@warden_required
def portal_verify_leave():
    return render_template('portal/verify_leave.html')

@app.route('/portal/leave-requests')
@warden_required
def portal_leave_requests():
    conn = database.get_db_connection()
    leaves = conn.execute("""
        SELECT l.*, s.first_name, s.last_name, s.prn, s.branch, s.hostel_name, s.room_number, s.contact, s.parent_contact
        FROM leave_requests l
        JOIN students s ON l.student_id = s.id
        ORDER BY l.applied_at DESC
    """).fetchall()
    conn.close()
    return render_template('portal/leave_requests.html', leaves=leaves)

@app.route('/portal/manage-users', methods=['GET', 'POST'])
@warden_required
def portal_manage_users():
    conn = database.get_db_connection()
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        role = request.form.get('role', 'warden')
        password = request.form.get('password', '').strip()

        existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            flash(f"Username '{username}' already exists!", 'error')
        else:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, email) VALUES (?, ?, ?, ?)",
                (username, generate_password_hash(password), role, email)
            )
            conn.commit()
            flash(f"Portal user '{username}' created successfully as {role.capitalize()}!", 'success')

    users = conn.execute("SELECT * FROM users WHERE role IN ('admin', 'warden') ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template('portal/manage_users.html', users=users)

@app.route('/portal/search-records')
@warden_required
def portal_search_records():
    search_query = request.args.get('q', '').strip()
    movement_filter = request.args.get('movement', '').strip()
    date_filter = request.args.get('date', '').strip()

    sql = """
        SELECT m.*, s.first_name, s.last_name, s.prn, s.branch, s.hostel_name, s.room_number
        FROM movement_logs m
        JOIN students s ON m.student_id = s.id
        WHERE 1=1
    """
    params = []

    if search_query:
        sql += " AND (s.first_name LIKE ? OR s.last_name LIKE ? OR s.prn LIKE ? OR s.hostel_name LIKE ?)"
        q_wild = f"%{search_query}%"
        params.extend([q_wild, q_wild, q_wild, q_wild])

    if movement_filter:
        sql += " AND m.movement_type = ?"
        params.append(movement_filter)

    if date_filter:
        sql += " AND date(m.timestamp) = date(?)"
        params.append(date_filter)

    sql += " ORDER BY m.timestamp DESC"

    conn = database.get_db_connection()
    logs = conn.execute(sql, params).fetchall()
    conn.close()

    return render_template(
        'portal/search_records.html',
        logs=logs,
        search_query=search_query,
        selected_movement=movement_filter,
        selected_date=date_filter
    )

# ==================== BIOMETRIC & LEAVE API ENDPOINTS ====================

@app.route('/api/face/enroll', methods=['POST'])
@login_required
def api_face_enroll():
    """Allows student or warden to update biometric face samples"""
    data = request.get_json() or {}
    student_id = data.get('student_id')
    samples = data.get('samples', [])

    # If student, ensure they can only update their own biometrics
    if session.get('role') == 'student':
        conn = database.get_db_connection()
        my_student = conn.execute("SELECT id FROM students WHERE user_id = ?", (session['user_id'],)).fetchone()
        conn.close()
        if not my_student or my_student['id'] != student_id:
            return jsonify({'status': 'error', 'message': 'Unauthorized to modify other biometrics'}), 403

    if not samples:
        return jsonify({'status': 'error', 'message': 'No face frames provided'}), 400

    success, msg = face_utils.save_face_samples(student_id, samples)
    if success:
        return jsonify({'status': 'success', 'message': msg})
    return jsonify({'status': 'error', 'message': msg}), 400

@app.route('/api/face/verify-gate', methods=['POST'])
@warden_required
def api_face_verify_gate():
    """Live camera frame verification endpoint at gate (Warden only)"""
    data = request.get_json() or {}
    image_b64 = data.get('image')
    if not image_b64:
        return jsonify({'found': False, 'message': 'No image frame received'}), 400

    match_result = face_utils.recognize_student_from_frame(image_b64)
    
    if not match_result.get('found') or not match_result.get('student'):
        return jsonify(match_result)

    student = match_result['student']
    student_id = student['id']

    # Check student leave status for today
    today_str = date.today().strftime('%Y-%m-%d')
    conn = database.get_db_connection()
    active_leave = conn.execute("""
        SELECT * FROM leave_requests
        WHERE student_id = ? AND status = 'Approved'
          AND leaving_date <= ? AND return_date >= ?
        ORDER BY id DESC LIMIT 1
    """, (student_id, today_str, today_str)).fetchone()
    conn.close()

    is_gate_open, time_str, gate_msg = face_utils.check_gate_time_status()
    is_authorized = bool(active_leave) and is_gate_open

    response = {
        'found': True,
        'student': student,
        'confidence': match_result.get('confidence', 0),
        'box': match_result.get('box'),
        'leave': dict(active_leave) if active_leave else None,
        'is_authorized': is_authorized,
        'gate_status': {
            'is_allowed': is_gate_open,
            'time_str': time_str,
            'message': gate_msg
        },
        'message': match_result.get('message')
    }
    return jsonify(response)

@app.route('/api/gate/log-movement', methods=['POST'])
@warden_required
def api_gate_log_movement():
    """Logs campus movement and triggers parent notifications (Warden only)"""
    data = request.get_json() or {}
    student_id = data.get('student_id')
    leave_id = data.get('leave_id')
    movement_type = data.get('movement_type', 'OUT') # 'OUT' or 'IN'
    is_authorized = data.get('authorized', True)
    confidence = data.get('confidence', 0.0)

    status_str = "Authorized" if is_authorized else "Unauthorized"
    is_open, _, _ = face_utils.check_gate_time_status()
    if not is_open:
        status_str = "Curfew/Late"

    conn = database.get_db_connection()
    conn.execute("""
        INSERT INTO movement_logs (student_id, leave_request_id, movement_type, status, confidence)
        VALUES (?, ?, ?, ?, ?)
    """, (student_id, leave_id, movement_type, status_str, confidence))
    conn.commit()

    # Get student & parent contacts
    student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    conn.close()

    if student:
        action_type = 'GATE_EXIT' if movement_type == 'OUT' else 'GATE_ENTRY'
        mail_utils.send_parent_notification(
            f"{student['first_name']} {student['last_name']}",
            student['parent_contact'],
            student['parent_email'],
            action_type,
            f"Gate status: {status_str} (Biometric Confidence: {confidence}%)"
        )

    return jsonify({'status': 'success', 'message': f'Gate movement logged successfully ({movement_type})'})

@app.route('/api/leave/update-status/<int:leave_id>', methods=['POST'])
@warden_required
def api_leave_update_status(leave_id):
    """Warden approve / reject leave application"""
    data = request.get_json() or {}
    new_status = data.get('status', 'Approved')
    rejection_reason = data.get('rejection_reason', '')

    conn = database.get_db_connection()
    conn.execute("""
        UPDATE leave_requests
        SET status = ?, rejection_reason = ?, reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (new_status, rejection_reason, session.get('username', 'warden'), leave_id))
    conn.commit()

    # Fetch student and send parent alert
    leave = conn.execute("""
        SELECT l.*, s.first_name, s.last_name, s.parent_contact, s.parent_email
        FROM leave_requests l
        JOIN students s ON l.student_id = s.id
        WHERE l.id = ?
    """, (leave_id,)).fetchone()
    conn.close()

    if leave:
        notif_action = 'LEAVE_APPROVED' if new_status == 'Approved' else 'LEAVE_REJECTED'
        details = f"{leave['leaving_date']} to {leave['return_date']}" if new_status == 'Approved' else rejection_reason
        mail_utils.send_parent_notification(
            f"{leave['first_name']} {leave['last_name']}",
            leave['parent_contact'],
            leave['parent_email'],
            notif_action,
            details
        )

    return jsonify({'status': 'success', 'message': f'Leave application {new_status}'})

if __name__ == '__main__':
    print("\n" + "="*60)
    print("[*] HOSTEL LEAVE & FACE RECOGNITION SYSTEM")
    print("[*] Anantha Lakshmi Institute of Technology and Sciences")
    print("="*60)
    print("[+] Web Portal running at: http://localhost:5000")
    print("[+] Student Login:        http://localhost:5000/login/student")
    print("[+] Warden/Admin Login:   http://localhost:5000/login/warden")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=False)
