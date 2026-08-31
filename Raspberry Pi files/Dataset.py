import os
import cv2
import numpy as np

# Ensure Dataset directory exists
os.makedirs('Dataset', exist_ok=True)

# Load Haar cascade classifier (with OpenCV default path fallback)
cascade_path = 'haarcascade_frontalface_default.xml'
if not os.path.exists(cascade_path):
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'

detector = cv2.CascadeClassifier(cascade_path)
cam = cv2.VideoCapture(0)

if not cam.isOpened():
    print("[!] Error: Could not open camera.")
    exit(1)

student_id = input('Enter your ID / Name: ').strip()
if not student_id:
    student_id = "sample_user"

sampleNum = 0
print(f"[*] Capturing face samples for ID: {student_id}. Look at the camera...")
print("[*] Press 'q' to stop early.")

while True:
    ret, img = cam.read()
    if not ret or img is None:
        print("[!] Failed to grab frame from camera.")
        break

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = detector.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5)

    for (x, y, w, h) in faces:
        cv2.rectangle(img, (x, y), (x + w, y + h), (255, 0, 0), 2)
        sampleNum += 1
        # Save face image
        file_path = os.path.join("Dataset", f"{student_id}_{sampleNum}.jpg")
        cv2.imwrite(file_path, gray[y:y+h, x:x+w])

        cv2.putText(img, f"Sample: {sampleNum}/30", (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    cv2.imshow('Face Dataset Capture', img)

    # Wait for key press or exit if 30 samples collected
    if cv2.waitKey(100) & 0xFF == ord('q'):
        break
    elif sampleNum >= 30:
        print(f"[+] Successfully captured {sampleNum} samples!")
        break

cam.release()
cv2.destroyAllWindows()

