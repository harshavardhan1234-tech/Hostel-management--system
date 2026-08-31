import os
import time
import datetime as dt
import logging as log
import cv2
import numpy as np

# Ensure log and dataset paths
log.basicConfig(filename='database.log', level=log.INFO)
dataset_dir = 'Dataset'
cascade_path = "haarcascade_frontalface_default.xml"
if not os.path.exists(cascade_path):
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'

faceCascade = cv2.CascadeClassifier(cascade_path)
recognizer = cv2.face.LBPHFaceRecognizer_create()

names = ['None', 'tasnim', 'Amir']

if not os.path.exists(dataset_dir) or len(os.listdir(dataset_dir)) == 0:
    print("[!] No dataset found in 'Dataset/' directory. Please run Dataset.py first to enroll faces.")
    exit(1)

images = []
labels = []
for filename in os.listdir(dataset_dir):
    if filename.endswith(('.jpg', '.png', '.jpeg')):
        file_path = os.path.join(dataset_dir, filename)
        im = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
        if im is not None:
            images.append(im)
            try:
                label_id = int(filename.split('_')[0]) if filename.split('_')[0].isdigit() else 1
            except Exception:
                label_id = 1
            labels.append(label_id)

if len(images) > 0:
    recognizer.train(images, np.array(labels))
    print("[+] Model training completed.")
else:
    print("[!] No valid face images found for training.")
    exit(1)

log_csv_path = "data_log.csv"
file = open(log_csv_path, "a")
font = cv2.FONT_HERSHEY_SIMPLEX
cap = cv2.VideoCapture(0)

print("[+] Camera started. Press ESC or 'q' to exit.")
log.info("Date Time , Student Name\n")
file.write("-------------------------------------------------\n")
file.write(f"        Date: {dt.datetime.now().strftime('%d-%m-%Y')}        \n")
file.write("-------------------------------------------------\n")
file.write("Time , Student Name\n")
file.flush()

while True:
    ret, frame = cap.read()
    if not ret or frame is None:
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = faceCascade.detectMultiScale(gray, 1.2, 5)

    for (x, y, w, h) in faces:
        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)
        label_pred, confidence = recognizer.predict(gray[y:y+h, x:x+w])

        # Confidence < 50 indicates good match with LBPH
        if confidence < 50:
            student_name = names[label_pred] if label_pred < len(names) else f"ID_{label_pred}"
            conf_str = f"  {round(100 - confidence)}%"
            log.info(f"{dt.datetime.now()},{student_name}\n")
            file.write(f"{dt.datetime.now().strftime('%H:%M:%S')},{student_name}\n")
            file.flush()
        else:
            student_name = "Unknown"
            conf_str = f"  {round(100 - confidence)}%"

        cv2.putText(frame, str(student_name), (x + 5, y - 5), font, 1, (255, 255, 255), 2)
        cv2.putText(frame, str(conf_str), (x + 5, y + h - 5), font, 1, (255, 255, 0), 1)

    cv2.imshow('Face Recognition', frame)
    k = cv2.waitKey(10) & 0xFF
    if k == 27 or k == ord('q'):
        break

file.close()
cap.release()
cv2.destroyAllWindows()