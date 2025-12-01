#!/usr/bin/env python3

import argparse
import base64
import json
import socket
import subprocess
import threading
import time
import re
from datetime import datetime

import board
import busio
import adafruit_bno055

# ---------- CONFIG ----------
FRAME_INTERVAL = 1.0  # seconds between frames
UWB_COMMAND = ["python", "-u", "nxp.py", "i", "100", "/dev/ttyUSB0"]
RUN_WINDOW_SEC = 5
I2C_ADDRESS = 0x28     # BNO055 addr
# ----------------------------

uwb_lock = threading.Lock()
uwb_last = {
    "timestamp": None,
    "distance_cm": None,
    "azimuth_deg": None,
    "elevation_deg": None,
    "nlos": None,
}
uwb_stop_event = threading.Event()


def get_imu_sensor():
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        sensor = adafruit_bno055.BNO055_I2C(i2c, address=I2C_ADDRESS)
        print("[IMU] BNO055 initialized")
        return sensor
    except Exception as e:
        print("[IMU] Could not init BNO055:", e)
        return None


def read_imu(sensor):
    if sensor is None:
        return {
            "timestamp": None,
            "temp_c": None,
            "heading": None,
            "roll": None,
            "pitch": None,
            "sys_cal": None,
            "gyro_cal": None,
            "accel_cal": None,
            "mag_cal": None,
        }

    ts = datetime.now().isoformat(timespec="milliseconds")
    try:
        temp = sensor.temperature
        euler = sensor.euler
        cal_sys, cal_gyro, cal_accel, cal_mag = sensor.calibration_status
        if euler is None:
            h = r = p = None
        else:
            h, r, p = euler
    except Exception as e:
        print("[IMU] Read error:", e)
        temp = h = r = p = cal_sys = cal_gyro = cal_accel = cal_mag = None

    return {
        "timestamp": ts,
        "temp_c": temp,
        "heading": h,
        "roll": r,
        "pitch": p,
        "sys_cal": cal_sys,
        "gyro_cal": cal_gyro,
        "accel_cal": cal_accel,
        "mag_cal": cal_mag,
    }


def run_uwb_once(data_pattern):
    print(f"[UWB] Starting: {' '.join(UWB_COMMAND)}")
    try:
        process = subprocess.Popen(
            UWB_COMMAND,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        print("[UWB] nxp.py not found")
        time.sleep(RUN_WINDOW_SEC)
        return

    start = time.time()
    try:
        while True:
            if uwb_stop_event.is_set():
                break

            if time.time() - start >= RUN_WINDOW_SEC:
                print(f"[UWB] {RUN_WINDOW_SEC}s window elapsed")
                break

            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    err = process.stderr.read()
                    if err:
                        print("[UWB] Exited early:\n", err)
                    break
                time.sleep(0.01)
                continue

            line = line.strip()
            print("[UWB]", line)
            m = data_pattern.search(line)
            if m:
                ts = datetime.now().isoformat(timespec="milliseconds")
                nlos = m.group(1)
                dist = m.group(2)
                az = m.group(3)
                el = m.group(4)
                with uwb_lock:
                    uwb_last["timestamp"] = ts
                    uwb_last["distance_cm"] = float(dist)
                    uwb_last["azimuth_deg"] = float(az)
                    uwb_last["elevation_deg"] = float(el)
                    uwb_last["nlos"] = int(nlos)
    finally:
        try:
            process.terminate()
        except Exception:
            pass
        try:
            process.wait(timeout=1)
        except Exception:
            pass
        print("[UWB] Cycle done")


def uwb_worker():
    pattern = re.compile(
        r"NLos:(\d+).*Dist:(\d+).*Azimuth:([-\d\.]+).*Elevation:([-\d\.]+)"
    )
    print("[UWB] Worker started")
    while not uwb_stop_event.is_set():
        run_uwb_once(pattern)
    print("[UWB] Worker stopped")


def capture_jpeg_bytes():
    """
    Capture a single JPEG frame from rpicam-still to stdout.
    """
    try:
        proc = subprocess.run(
            ["rpicam-still", "-n", "-t", "1", "-o", "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return proc.stdout
    except FileNotFoundError:
        raise SystemExit(
            "rpicam-still not found. Install rpicam-apps:\n"
            "  sudo apt install -y rpicam-apps"
        )
    except subprocess.CalledProcessError as e:
        print("[CAM] Error running rpicam-still:", e.stderr.decode(errors="ignore"))
        return None


def main():
    parser = argparse.ArgumentParser(description="Pi node streaming client")
    parser.add_argument("--server-ip", required=True, help="Desktop server IP")
    parser.add_argument("--server-port", type=int, default=5000)
    parser.add_argument("--node-id", required=True, help="Unique node id (e.g., pi1)")
    parser.add_argument("--interval", type=float, default=FRAME_INTERVAL)
    args = parser.parse_args()

    # Connect to desktop
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print(f"[NET] Connecting to {args.server_ip}:{args.server_port} ...")
    sock.connect((args.server_ip, args.server_port))
    f = sock.makefile("w")  # text mode for JSON lines
    print("[NET] Connected")

    # Start IMU
    imu_sensor = get_imu_sensor()

    # Start UWB thread
    t_uwb = threading.Thread(target=uwb_worker, daemon=True)
    t_uwb.start()

    try:
        while True:
            ts = datetime.now().isoformat(timespec="milliseconds")

            # 1) Capture image
            jpeg_bytes = capture_jpeg_bytes()
            if jpeg_bytes is None:
                time.sleep(args.interval)
                continue
            img_b64 = base64.b64encode(jpeg_bytes).decode("ascii")

            # 2) Read IMU
            imu = read_imu(imu_sensor)

            # 3) Snapshot UWB
            with uwb_lock:
                uwb = uwb_last.copy()

            # 4) Build message
            msg = {
                "node_id": args.node_id,
                "timestamp": ts,
                "imu": imu,
                "uwb": uwb,
                "image_b64": img_b64,
            }

            # 5) Send as JSON line
            line = json.dumps(msg) + "\n"
            f.write(line)
            f.flush()

            print(f"[SEND] Sent frame from {args.node_id} @ {ts}")
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n[MAIN] Ctrl+C, stopping...")
    finally:
        uwb_stop_event.set()
        try:
            sock.close()
        except Exception:
            pass
        print("[MAIN] Exiting")


if __name__ == "__main__":
    main()
