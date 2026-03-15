import cv2
import numpy as np
import dlib
from imutils import face_utils
import requests
import os
import time

# ===================================================================
# DROWSINESS DETECTION SYSTEM - PYTHON CODE v2.0
# ===================================================================

# --- CONFIGURATION ---
ESP32_IP = "http://10.196.34.15"    # ⚠ UPDATE THIS with your ESP32's IP address

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
DLIB_MODEL_PATH = os.path.join(SCRIPT_DIR, "shape_predictor_68_face_landmarks.dat")

# Camera settings
CAMERA_INDEX = 0
FRAME_RESIZE_WIDTH = 480

# Detection thresholds
EYE_CLOSED_FRAMES_DROWSY = 15    # ~0.5 seconds at 30fps
EYE_CLOSED_FRAMES_SLEEPING = 45  # ~1.5 seconds at 30fps
EAR_THRESH_CLOSED = 0.25         # Eye Aspect Ratio threshold

# ===================================================================
# FUNCTIONS
# ===================================================================

def compute_ear(eye_points):
    """Calculate Eye Aspect Ratio (EAR) for drowsiness detection"""
    # Compute vertical eye distances
    v1 = np.linalg.norm(eye_points[1] - eye_points[5])
    v2 = np.linalg.norm(eye_points[2] - eye_points[4])
    # Compute horizontal eye distance
    h = np.linalg.norm(eye_points[0] - eye_points[3])
    # Calculate EAR
    ear = (v1 + v2) / (2.0 * h)
    return ear

def send_esp_command(command):
    """Send command to ESP32 via HTTP"""
    try:
        url = ESP32_IP + command
        response = requests.get(url, timeout=1)
        if response.status_code == 200:
            print(f"✓ Sent: {command}")
            return True
        else:
            print(f"✗ Failed: {command} (Status: {response.status_code})")
            return False
    except requests.exceptions.RequestException as e:
        print(f"✗ Connection Error: {e}")
        return False

# ===================================================================
# INITIALIZATION
# ===================================================================

print("="*70)
print("          DROWSINESS DETECTION SYSTEM v2.0")
print("="*70)

# Validate dlib model
if not os.path.exists(DLIB_MODEL_PATH):
    print(f"❌ ERROR: Dlib model not found!")
    print(f"   Expected location: {DLIB_MODEL_PATH}")
    print(f"   Download from: http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2")
    print(f"   Extract the .bz2 file and place the .dat file in the same folder as this script.")
    exit(1)

# Initialize camera
print("📷 Initializing camera...")
cap = cv2.VideoCapture(CAMERA_INDEX)
if not cap.isOpened():
    print(f"❌ ERROR: Cannot open camera at index {CAMERA_INDEX}")
    exit(1)

# Set camera properties for better performance
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_FPS, 30)

print("✓ Camera initialized")

# Initialize face detector and predictor
print("🧠 Loading face detection model...")
detector = dlib.get_frontal_face_detector()
predictor = dlib.shape_predictor(DLIB_MODEL_PATH)
(lStart, lEnd) = face_utils.FACIAL_LANDMARKS_IDXS["left_eye"]
(rStart, rEnd) = face_utils.FACIAL_LANDMARKS_IDXS["right_eye"]
print("✓ Face detection model loaded")

# Test ESP32 connection
print(f"🌐 Testing connection to ESP32 at {ESP32_IP}...")
if send_esp_command("/safe"):
    print("✓ ESP32 connection successful")
else:
    print("⚠  WARNING: Cannot connect to ESP32")
    print("   Please check:")
    print("   1. ESP32 is powered on and running")
    print("   2. ESP32 IP address is correct in the code")
    print("   3. Both devices are on the same WiFi network")
    print("   4. Check the Serial Monitor on Arduino IDE for ESP32's IP")
    response = input("\n   Continue anyway? (y/n): ")
    if response.lower() != 'y':
        cap.release()
        exit(1)

print("\n" + "="*70)
print("✓ System Ready! Press 'ESC' or 'Q' to quit")
print("="*70 + "\n")

# ===================================================================
# STATE VARIABLES
# ===================================================================

consecutive_frames_closed = 0
current_state = "safe"  # Can be: "safe", "drowsy", "sleeping"
frame_counter = 0
last_command_time = 0
COMMAND_COOLDOWN = 0.5  # Minimum time between commands (seconds)

# Initialize variables for EAR display
avg_ear = 0.0

# ===================================================================
# MAIN DETECTION LOOP
# ===================================================================

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Failed to read frame from camera")
            break

        frame_counter += 1
        
        # Resize frame for faster processing
        h, w = frame.shape[:2]
        aspect_ratio = w / h
        new_height = int(FRAME_RESIZE_WIDTH / aspect_ratio)
        resized_frame = cv2.resize(frame, (FRAME_RESIZE_WIDTH, new_height))
        gray = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2GRAY)
        
        # Detect faces
        faces = detector(gray, 0)

        # Initialize display variables
        status = "No Face Detected"
        status_color = (0, 255, 255)  # Yellow
        
        if not faces:
            # No face detected
            consecutive_frames_closed = 0
            avg_ear = 0.0
            
            # Return to safe state if face is lost
            if current_state != "safe":
                current_time = time.time()
                if current_time - last_command_time > COMMAND_COOLDOWN:
                    print("\n⚠  Face lost - Returning to safe state")
                    send_esp_command("/safe")
                    current_state = "safe"
                    last_command_time = current_time
        else:
            # Face detected - process landmarks
            face = faces[0]
            shape = predictor(gray, face)
            shape = face_utils.shape_to_np(shape)
            
            # Extract eye landmarks
            leftEye = shape[rStart:rEnd]  # Swapped to correct mapping
            rightEye = shape[lStart:lEnd]  # Swapped to correct mapping
            
            # Calculate EAR for both eyes
            leftEAR = compute_ear(leftEye)
            rightEAR = compute_ear(rightEye)
            avg_ear = (leftEAR + rightEAR) / 2.0

            # Update closed frame counter
            if avg_ear < EAR_THRESH_CLOSED:
                consecutive_frames_closed += 1
            else:
                consecutive_frames_closed = 0

            # Determine state and send commands
            current_time = time.time()
            
            if consecutive_frames_closed >= EYE_CLOSED_FRAMES_SLEEPING:
                # SLEEPING STATE
                status = "SLEEPING !!!"
                status_color = (0, 0, 255)  # Red
                
                if current_state != "sleeping" and current_time - last_command_time > COMMAND_COOLDOWN:
                    print(f"\n🚨 SLEEPING DETECTED! (Frame: {frame_counter})")
                    send_esp_command("/sleeping")
                    current_state = "sleeping"
                    last_command_time = current_time
            
            elif consecutive_frames_closed >= EYE_CLOSED_FRAMES_DROWSY:
                # DROWSY STATE
                status = "DROWSY!"
                status_color = (0, 165, 255)  # Orange
                
                if current_state != "drowsy" and current_time - last_command_time > COMMAND_COOLDOWN:
                    print(f"\n⚠  DROWSY DETECTED! (Frame: {frame_counter})")
                    send_esp_command("/drowsy")
                    current_state = "drowsy"
                    last_command_time = current_time
            
            else:
                # SAFE STATE
                status = "Active"
                status_color = (0, 255, 0)  # Green
                
                if current_state != "safe" and current_time - last_command_time > COMMAND_COOLDOWN:
                    print(f"\n✓ Driver AWAKE (Frame: {frame_counter})")
                    send_esp_command("/safe")
                    current_state = "safe"
                    last_command_time = current_time

            # Draw eye contours for debugging
            leftEyeHull = cv2.convexHull(leftEye)
            rightEyeHull = cv2.convexHull(rightEye)
            cv2.drawContours(frame, [leftEyeHull], -1, (0, 255, 0), 1)
            cv2.drawContours(frame, [rightEyeHull], -1, (0, 255, 0), 1)

        # Display status on frame
        cv2.putText(frame, status, (10, 40), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, status_color, 3)
        
        # Display additional info
        if faces:
            info_text = f"EAR: {avg_ear:.3f} | Closed Frames: {consecutive_frames_closed}"
        else:
            info_text = "No Face Detected"
        cv2.putText(frame, info_text, (10, frame.shape[0] - 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Display warning messages
        if status == "SLEEPING !!!":
            cv2.putText(frame, "WAKE UP NOW!", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, status_color, 3)
        elif status == "DROWSY!":
            cv2.putText(frame, "Stay Alert!", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, status_color, 3)

        # Display current state
        state_text = f"State: {current_state.upper()}"
        cv2.putText(frame, state_text, (10, frame.shape[0] - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
        
        # Display instructions
        cv2.putText(frame, "Press 'ESC' or 'Q' to Quit", (10, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Show frame
        cv2.imshow("Drowsiness Detection System", frame)

        # Check for ESC or Q key
        key = cv2.waitKey(1) & 0xFF
        if key == 27 or key == ord('q') or key == ord('Q'):  # ESC or Q key
            print("\n\n👋 Exiting system...")
            break

except KeyboardInterrupt:
    print("\n\n⚠  Interrupted by user (Ctrl+C)")

finally:
    # Cleanup
    print("\n🔧 Cleaning up...")
    
    # Send safe command before exiting
    if current_state != "safe":
        print("📤 Sending final safe command to ESP32...")
        send_esp_command("/safe")
        time.sleep(0.5)
    
    cap.release()
    cv2.destroyAllWindows()
    
    print("\n" + "="*70)
    print("          ✓ System Shutdown Complete")
    print("="*70)
    print("\nThank you for using the Drowsiness Detection System!")