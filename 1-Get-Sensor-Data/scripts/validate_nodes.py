import subprocess
import threading
import time
import csv
import re
import cv2
import pandas as pd
from datetime import datetime
import queue
from picamera.array import PiRGBArray
from picamera import PiCamera

# ==========================================
# CONFIGURATION
# ==========================================
UWB_SCRIPT_PATH = "nxp.py"
UWB_COM_PORT = "/dev/ttyUSB0"  # Change to your actual port (e.g., /dev/ttyUSB0 on Linux)
OUTPUT_CSV = "sensor_fusion_data.csv"
IMAGE_FOLDER = "captured_images"

# Create image folder if it doesn't exist
import os
if not os.path.exists(IMAGE_FOLDER):
    os.makedirs(IMAGE_FOLDER)

# Global variables to hold the latest data from each sensor
latest_data = {
    "timestamp": None,
    "uwb_dist": None,
    "uwb_azimuth": None,
    "uwb_elevation": None,
    "imu_acc_x": 0, "imu_acc_y": 0, "imu_acc_z": 0,
    "imu_gyro_x": 0, "imu_gyro_y": 0, "imu_gyro_z": 0,
    "image_filename": None
}

# Thread locking to prevent reading data while it's being written
data_lock = threading.Lock()
stop_event = threading.Event()

# ==========================================
# 1. UWB WORKER (Subprocess Wrapper)
# ==========================================
def uwb_worker():
    """
    Runs the nxp.py script as a subprocess and parses its print output.
    Looks for lines starting with *** to extract data.
    """
    # Command to run the existing script. Add arguments if needed.
    cmd = ["python", UWB_SCRIPT_PATH, "r", UWB_COM_PORT]
    
    print(f"[UWB] Starting UWB subprocess: {' '.join(cmd)}")
    
    # Start the subprocess with pipes for stdout
    process = subprocess.Popen(
        cmd, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE, 
        text=True, 
        bufsize=1
    )

    # Regex to parse the specific output line from nxp.py
    # Example: ***(105) NLos:0 Dist:250 Azimuth:12.5 (FOM:1) Elevation:5.0 (FOM:1)...
    pattern = re.compile(r"\*\*\*.*Dist:(\d+).*Azimuth:([-\d\.]+).*Elevation:([-\d\.]+)")

    try:
        while not stop_event.is_set():
            line = process.stdout.readline()
            if not line:
                break
            
            # Check if this line contains our data
            match = pattern.search(line)
            if match:
                dist = int(match.group(1))
                azimuth = float(match.group(2))
                elevation = float(match.group(3))
                
                with data_lock:
                    latest_data["uwb_dist"] = dist
                    latest_data["uwb_azimuth"] = azimuth
                    latest_data["uwb_elevation"] = elevation
            
            # Optional: Print raw line for debug
            # print(f"[UWB RAW] {line.strip()}")

    except Exception as e:
        print(f"[UWB] Error: {e}")
    finally:
        process.terminate()
        print("[UWB] Subprocess terminated.")

# ==========================================
# 2. CAMERA WORKER
# ==========================================
def camera_worker():
    """
    Captures frames specifically using the Raspberry Pi Camera Module.
    """
    try:
        # Initialize Pi Camera
        camera = PiCamera()
        camera.resolution = (640, 480) # Lower res is faster for logging
        camera.framerate = 30
        
        # Allow the camera to warmup
        time.sleep(2)
        
        print("[Camera] Pi Camera recording started.")
        
        # Raw capture is faster than encoding to JPG in memory repeatedly
        rawCapture = PiRGBArray(camera, size=(640, 480))
        
        frame_idx = 0
        
        # capture_continuous is the most efficient method for video on Pi
        for frame_obj in camera.capture_continuous(rawCapture, format="bgr", use_video_port=True):
            if stop_event.is_set():
                break
            
            # Grab the NumPy array representing the image
            image = frame_obj.array
            
            # Generate filename
            ts = datetime.now().strftime("%H%M%S_%f")
            filename = f"{IMAGE_FOLDER}/img_{ts}.jpg"
            
            # Save to disk
            cv2.imwrite(filename, image)
            
            # Update the global data variable for the CSV logger
            with data_lock:
                latest_data["image_filename"] = filename
            
            # Clear the stream in preparation for the next frame
            rawCapture.truncate(0)
            
            frame_idx += 1
            
    except Exception as e:
        print(f"[Camera] Error: {e}")
    finally:
        try:
            camera.close()
        except:
            pass
        print("[Camera] Released.")

# ==========================================
# 3. IMU WORKER (Placeholder)
# ==========================================
def imu_worker():
    """
    Reads from your IMU. 
    REPLACE THIS with your specific IMU library code (e.g., Serial, BNO055, MPU6050).
    """
    print("[IMU] Listener started (Mock Mode).")
    
    while not stop_event.is_set():
        # --- REPLACE THIS BLOCK WITH REAL READ CODE ---
        import random
        acc_x = random.uniform(-1, 1)
        acc_y = random.uniform(-1, 1)
        acc_z = 9.8 + random.uniform(-0.1, 0.1)
        # ----------------------------------------------

        with data_lock:
            latest_data["imu_acc_x"] = acc_x
            latest_data["imu_acc_y"] = acc_y
            latest_data["imu_acc_z"] = acc_z
        
        # IMUs are fast, usually 100Hz+
        time.sleep(0.01)

# ==========================================
# MAIN LOOP (The CSV Writer)
# ==========================================
def main():
    # Start sensor threads
    t_uwb = threading.Thread(target=uwb_worker)
    t_cam = threading.Thread(target=camera_worker)
    t_imu = threading.Thread(target=imu_worker)

    t_uwb.start()
    t_cam.start()
    t_imu.start()

    print(f"Logging data to {OUTPUT_CSV}... Press Ctrl+C to stop.")

    # Open CSV for writing
    with open(OUTPUT_CSV, mode='w', newline='') as file:
        fieldnames = [
            'timestamp', 
            'uwb_dist_cm', 'uwb_azimuth_deg', 'uwb_elevation_deg',
            'imu_acc_x', 'imu_acc_y', 'imu_acc_z',
            'image_file'
        ]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        try:
            while True:
                # Synchronization Rate: e.g., 10Hz (0.1s) or 30Hz (0.033s)
                # We sample the "Current State" of all sensors at this rate.
                time.sleep(0.1) 

                current_row = {}
                with data_lock:
                    current_row['timestamp'] = datetime.now().isoformat()
                    current_row['uwb_dist_cm'] = latest_data["uwb_dist"]
                    current_row['uwb_azimuth_deg'] = latest_data["uwb_azimuth"]
                    current_row['uwb_elevation_deg'] = latest_data["uwb_elevation"]
                    current_row['imu_acc_x'] = latest_data["imu_acc_x"]
                    current_row['imu_acc_y'] = latest_data["imu_acc_y"]
                    current_row['imu_acc_z'] = latest_data["imu_acc_z"]
                    current_row['image_file'] = latest_data["image_filename"]
                
                # Only write if we have at least getting SOME data (optional check)
                writer.writerow(current_row)
                file.flush() # Ensure data is written immediately

        except KeyboardInterrupt:
            print("\nStopping logging...")
            stop_event.set()

    # Wait for threads to finish
    t_uwb.join()
    t_cam.join()
    t_imu.join()
    print("Done.")

if __name__ == "__main__":
    main()