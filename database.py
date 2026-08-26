import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "hostel.db")

def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db_connection()
    cursor = conn.cursor()

    # Users Table (authentication)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student', -- 'student', 'warden', 'admin'
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Students Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            prn TEXT UNIQUE NOT NULL,
            first_name TEXT NOT NULL,
            middle_name TEXT DEFAULT '',
            last_name TEXT NOT NULL,
            gender TEXT,
            dob TEXT,
            branch TEXT,
            year TEXT,
            hostel_name TEXT,
            room_number TEXT,
            address TEXT,
            city TEXT,
            state TEXT,
            zip_code TEXT,
            contact TEXT,
            parent_name TEXT DEFAULT 'Parent/Guardian',
            parent_contact TEXT,
            parent_email TEXT,
            face_enrolled INTEGER DEFAULT 0,
            samples_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)

    # Leave Requests Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leave_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            leave_type TEXT NOT NULL,
            leaving_date TEXT NOT NULL,
            return_date TEXT NOT NULL,
            period TEXT NOT NULL,
            total_days INTEGER DEFAULT 1,
            reason TEXT NOT NULL,
            permission_from TEXT NOT NULL,
            address_during_leave TEXT,
            status TEXT DEFAULT 'Pending', -- 'Pending', 'Approved', 'Rejected', 'Completed'
            rejection_reason TEXT,
            verified_by_face INTEGER DEFAULT 0,
            reviewed_by TEXT,
            reviewed_at TIMESTAMP,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE
        )
    """)

    # Gate Movement & Attendance Logs Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movement_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            leave_request_id INTEGER,
            movement_type TEXT NOT NULL, -- 'OUT', 'IN'
            status TEXT NOT NULL, -- 'Authorized', 'Unauthorized', 'Late'
            confidence REAL DEFAULT 0.0,
            verification_method TEXT DEFAULT 'Face Recognition',
            remarks TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE,
            FOREIGN KEY (leave_request_id) REFERENCES leave_requests (id) ON DELETE SET NULL
        )
    """)

    # System Settings Table (e.g., Gate Hours)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Default Gate Configuration
    cursor.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('gate_open_time', '06:00')")
    cursor.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('gate_close_time', '22:00')")
    cursor.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('parent_sms_enabled', '1')")
    cursor.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('parent_email_enabled', '1')")

    # Seed Default Warden & Admin
    admin_user = cursor.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
    if not admin_user:
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, email) VALUES (?, ?, ?, ?)",
            ("admin", generate_password_hash("admin123"), "admin", "admin@hostel.edu")
        )

    warden_user = cursor.execute("SELECT id FROM users WHERE username = 'warden'").fetchone()
    if not warden_user:
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, email) VALUES (?, ?, ?, ?)",
            ("warden", generate_password_hash("warden123"), "warden", "warden@hostel.edu")
        )

    # Seed sample student for quick testing if table empty
    sample_student = cursor.execute("SELECT id FROM students WHERE prn = '2026WCECS001'").fetchone()
    if not sample_student:
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, email) VALUES (?, ?, ?, ?)",
            ("student1", generate_password_hash("student123"), "student", "apurva@student.wce.edu")
        )
        u_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO students (
                user_id, prn, first_name, middle_name, last_name, gender, dob, branch, year,
                hostel_name, room_number, address, city, state, zip_code, contact,
                parent_name, parent_contact, parent_email, face_enrolled, samples_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            u_id, '2026WCECS001', 'Apurva', 'S', 'Patil', 'female', '2004-05-14',
            'Computer Science and Engineering', 'Third Year', 'D1', '104',
            'WCE Campus Hostel', 'Sangli', 'Maharashtra', '416415', '9876543210',
            'S. Patil', '9763978679', 'parent.patil@gmail.com', 0, 0
        ))
        s_id = cursor.lastrowid
        
        # Sample Leave Application
        cursor.execute("""
            INSERT INTO leave_requests (
                student_id, leave_type, leaving_date, return_date, period, total_days,
                reason, permission_from, address_during_leave, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            s_id, 'Vacation', datetime.now().strftime('%Y-%m-%d'), 
            datetime.now().strftime('%Y-%m-%d'), 'Full day', 2,
            'Attending family function in hometown', 'Warden',
            '12, Shivajinagar, Kolhapur, Maharashtra', 'Approved'
        ))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
