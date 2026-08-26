import os
import requests
import datetime

# SMS / Email Dispatch helper

def send_parent_notification(student_name, parent_contact, parent_email, action_type, details=None):
    """
    Sends automated parent notifications (Email & SMS simulation).
    action_type: 'LEAVE_APPLIED', 'LEAVE_APPROVED', 'LEAVE_REJECTED', 'GATE_EXIT', 'GATE_ENTRY'
    """
    now_str = datetime.datetime.now().strftime("%d-%b-%Y %I:%M %p")
    
    subject = f"Hostel Notification: {student_name} - {action_type.replace('_', ' ')}"
    
    if action_type == 'LEAVE_APPLIED':
        message = f"Dear Parent, your ward {student_name} has submitted a hostel leave application on {now_str}. Details: {details or 'Awaiting warden approval'}."
    elif action_type == 'LEAVE_APPROVED':
        message = f"Dear Parent, the leave request for {student_name} has been APPROVED by the hostel warden. Valid from {details or 'scheduled dates'}."
    elif action_type == 'LEAVE_REJECTED':
        message = f"Dear Parent, the leave request for {student_name} was REJECTED. Reason: {details or 'Administrative rules'}."
    elif action_type == 'GATE_EXIT':
        message = f"ALERT: Your ward {student_name} has EXITED the hostel campus through biometric face verification on {now_str}. Reason/Pass: {details or 'Approved Leave'}."
    elif action_type == 'GATE_ENTRY':
        message = f"ALERT: Your ward {student_name} has safely ENTERED the hostel campus on {now_str}."
    else:
        message = f"Hostel Notification regarding {student_name}: {details} ({now_str})"

    # Log notification to console / simulated inbox
    print(f"\n[NOTIF-DISPATCH] To Parent: {parent_contact} | Email: {parent_email}")
    print(f"[SUBJECT]: {subject}")
    print(f"[MESSAGE]: {message}\n")

    # Optional live SMS via Fast2SMS if token is set in environment or default
    sms_sent = False
    fast2sms_key = os.environ.get("FAST2SMS_API_KEY", "")
    if fast2sms_key and parent_contact:
        try:
            url = "https://www.fast2sms.com/dev/bulk"
            payload = f"sender_id=FSTSMS&message={message}&language=english&route=p&numbers={parent_contact}"
            headers = {
                'authorization': fast2sms_key,
                'Content-Type': "application/x-www-form-urlencoded",
                'Cache-Control': "no-cache"
            }
            resp = requests.post(url, data=payload, headers=headers, timeout=5)
            if resp.status_code == 200:
                sms_sent = True
        except Exception as e:
            print(f"[SMS ERROR]: {e}")

    return {
        "status": "success",
        "message": message,
        "sms_sent": sms_sent,
        "email_logged": True,
        "timestamp": now_str
    }
