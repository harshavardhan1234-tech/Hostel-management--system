import os
import cv2
import numpy as np
import base64
import re
from datetime import datetime
from PIL import Image
import database

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HAAR_PATHS = [
    os.path.join(BASE_DIR, "haarcascade_frontalface_default.xml"),
    os.path.join(BASE_DIR, "FRAS", "haarcascade_frontalface_default.xml"),
    os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml") if hasattr(cv2, 'data') else ""
]

HAAR_FILE = next((p for p in HAAR_PATHS if os.path.isfile(p)), None)
TRAINING_DIR = os.path.join(BASE_DIR, "data", "training_images")
MODEL_DIR = os.path.join(BASE_DIR, "data", "trained_model")
MODEL_PATH = os.path.join(MODEL_DIR, "trainer.yml")

os.makedirs(TRAINING_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

def get_face_detector():
    if HAAR_FILE and os.path.exists(HAAR_FILE):
        return cv2.CascadeClassifier(HAAR_FILE)
    if hasattr(cv2, 'data') and os.path.exists(os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')):
        return cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml'))
    return None

def decode_base64_image(base64_str):
    """Converts a base64 data URL string into an OpenCV BGR image"""
    try:
        if "," in base64_str:
            base64_str = base64_str.split(",")[1]
        image_data = base64.b64decode(base64_str)
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        print(f"Error decoding image: {e}")
        return None

def detect_faces_in_image(img):
    """Detects faces in OpenCV image, returns gray image and list of (x, y, w, h) boxes"""
    detector = get_face_detector()
    if detector is None or img is None:
        return None, []
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = detector.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60))
    return gray, faces

def save_face_samples(student_id, base64_images):
    """Saves multiple face crops from base64 frames for a student and triggers training"""
    detector = get_face_detector()
    if detector is None:
        return False, "Face detector cascade not loaded."

    saved_count = 0
    # Clear previous samples for this student if any
    for f in os.listdir(TRAINING_DIR):
        if f.startswith(f"student_{student_id}_"):
            try:
                os.remove(os.path.join(TRAINING_DIR, f))
            except Exception:
                pass

    for idx, b64 in enumerate(base64_images):
        img = decode_base64_image(b64)
        if img is None:
            continue
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = detector.detectMultiScale(gray, 1.2, 5, minSize=(50, 50))
        
        for (x, y, w, h) in faces:
            face_roi = gray[y:y+h, x:x+w]
            face_roi = cv2.resize(face_roi, (200, 200))
            filename = f"student_{student_id}_{saved_count + 1}.jpg"
            cv2.imwrite(os.path.join(TRAINING_DIR, filename), face_roi)
            saved_count += 1
            break # one face per frame is enough

    if saved_count > 0:
        # Update student record
        conn = database.get_db_connection()
        conn.execute(
            "UPDATE students SET face_enrolled = 1, samples_count = ? WHERE id = ?",
            (saved_count, student_id)
        )
        conn.commit()
        conn.close()

        # Re-train model
        train_success, train_msg = train_face_recognizer()
        return True, f"Successfully captured {saved_count} face samples. {train_msg}"
    
    return False, "No valid faces detected in the provided video frames. Please face the camera with good lighting."

def train_face_recognizer():
    """Trains the LBPH recognizer on all stored samples in data/training_images/"""
    image_files = [f for f in os.listdir(TRAINING_DIR) if f.endswith(".jpg") or f.endswith(".png")]
    if not image_files:
        return False, "No training samples found in dataset."

    faces = []
    ids = []

    for img_name in image_files:
        # Expected format: student_{id}_{sample_idx}.jpg
        match = re.match(r"student_(\d+)_\d+\.jpg", img_name)
        if not match:
            continue
        s_id = int(match.group(1))
        img_path = os.path.join(TRAINING_DIR, img_name)
        
        try:
            pil_img = Image.open(img_path).convert('L')
            img_np = np.array(pil_img, 'uint8')
            faces.append(img_np)
            ids.append(s_id)
        except Exception as e:
            print(f"Error loading {img_path}: {e}")

    if not faces:
        return False, "No valid face samples parsed for training."

    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.train(faces, np.array(ids))
        recognizer.save(MODEL_PATH)
        return True, f"Trained model with {len(faces)} samples across {len(set(ids))} students."
    except Exception as e:
        return False, f"Model training error: {str(e)}"

def recognize_student_from_frame(base64_str):
    """
    Receives live camera frame, detects face, matches against trained model.
    Returns:
      result dict {
        'found': bool,
        'student': dict or None,
        'confidence': float,
        'box': [x, y, w, h],
        'status': str,
        'message': str
      }
    """
    img = decode_base64_image(base64_str)
    if img is None:
        return {'found': False, 'message': 'Invalid image data'}

    gray, faces = detect_faces_in_image(img)
    if len(faces) == 0:
        return {'found': False, 'message': 'No face detected. Please position face inside the box.'}

    if not os.path.exists(MODEL_PATH):
        # Model hasn't been trained yet
        x, y, w, h = [int(v) for v in faces[0]]
        return {
            'found': False,
            'box': [x, y, w, h],
            'message': 'Face detected, but biometric model is not trained yet. Register students first.'
        }

    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.read(MODEL_PATH)
    except Exception as e:
        return {'found': False, 'message': f'Error loading trained model: {e}'}

    best_match = None
    best_conf_score = 0.0

    for (x, y, w, h) in faces:
        face_roi = gray[y:y+h, x:x+w]
        face_roi = cv2.resize(face_roi, (200, 200))
        predicted_id, distance = recognizer.predict(face_roi)
        
        # LBPH distance: 0 is perfect match, > 80 is poor match
        # Convert distance to confidence percentage:
        confidence = max(0, min(100, round(100 - distance, 1)))

        if distance < 75: # confidence > 25% threshold
            conn = database.get_db_connection()
            student = conn.execute("SELECT * FROM students WHERE id = ?", (predicted_id,)).fetchone()
            conn.close()

            if student:
                student_dict = dict(student)
                return {
                    'found': True,
                    'student': student_dict,
                    'confidence': confidence,
                    'box': [int(x), int(y), int(w), int(h)],
                    'message': f"Recognized: {student['first_name']} {student['last_name']} ({confidence}% match)"
                }
        
        return {
            'found': False,
            'box': [int(x), int(y), int(w), int(h)],
            'confidence': confidence,
            'message': 'Face detected, but student record not matched (Unknown).'
        }

    return {'found': False, 'message': 'No matching face identified.'}

def check_gate_time_status():
    """
    Checks if current system time is allowed for students leaving/entering.
    Returns (is_allowed: bool, current_time_str: str, message: str)
    """
    now = datetime.now()
    current_time = now.time()
    
    conn = database.get_db_connection()
    open_setting = conn.execute("SELECT value FROM system_settings WHERE key = 'gate_open_time'").fetchone()
    close_setting = conn.execute("SELECT value FROM system_settings WHERE key = 'gate_close_time'").fetchone()
    conn.close()

    open_str = open_setting['value'] if open_setting else "06:00"
    close_str = close_setting['value'] if close_setting else "22:00"

    open_t = datetime.strptime(open_str, "%H:%M").time()
    close_t = datetime.strptime(close_str, "%H:%M").time()

    is_allowed = (open_t <= current_time <= close_t)
    time_display = now.strftime("%I:%M %p")
    
    if is_allowed:
        return True, time_display, f"Gate is OPEN (Allowed hours: {open_str} - {close_str})"
    else:
        return False, time_display, f"Gate is CLOSED! Current time ({time_display}) is outside authorized hours ({open_str} - {close_str}). Special warden permission required."
