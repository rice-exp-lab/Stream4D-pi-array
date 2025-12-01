#!/usr/bin/env python3

import argparse
import base64
import csv
import json
import re
import socket
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import board
import busio
import adafruit_bno055

# ===================== CONFIG =====================

# --- Camera / capture ---
DEFAULT_INTERVAL = 1.0      # seconds between frames
DEFAULT_COUNT = 100         # number of frames

# --- IMU (BNO055) ---
I2C_ADDRESS = 0x28          # change to 0x29 if needed

# --- UWB / NXP ---
UWB_COMMAND = ["python", "-u", "nxp.py", "i", "100", "/dev/ttyUSB0"]
RUN_WINDOW_SEC = 5          # run nxp.py for 5 seconds per cycle

# ==================================================

# Shared UWB state (latest reading)
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
    """Initialize and return BNO055 sensor, or None if it fails."""
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        sensor = adafruit_bno055.BNO055_I2C(i2c, address=I2C_ADDRESS)
        print("[IMU] BNO055 initialized.")
        return sensor
    except Exception as e:
        print("[IMU] CRITICAL ERROR: Could not connect to BNO055.")
        print("      Error details:", e)
        print("      IMU fields will be blank.")
        return None


def read_imu(sensor):
    """Read one IMU sample. Returns a dict; values may be None if unavailable."""
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
        euler = sensor.euler  # (heading, roll, pitch) or None
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
    """
    Run nxp.py once for RUN_WINDOW_SEC seconds,
    update uwb_last with the most recent reading seen,
    then stop the process.
    """
    print(f"\n[UWB] Starting: {' '.join(UWB_COMMAND)}")
    try:
        process = subprocess.Popen(
            UWB_COMMAND,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # line-buffered
        )
    except FileNotFoundError:
        print("[UWB] ERROR: Could not start nxp.py (FileNotFoundError).")
        time.sleep(RUN_WINDOW_SEC)
        return

    start_time = time.time()

    try:
        while True:
            if uwb_stop_event.is_set():
                break

            # Stop after RUN_WINDOW_SEC seconds
            if time.time() - start_time >= RUN_WINDOW_SEC:
                print(f"[UWB] {RUN_WINDOW_SEC}s window elapsed, restarting soon...")
                break

            line = process.stdout.readline()

            if not line:
                if process.poll() is not None:
                    # Process exited early
                    err = process.stderr.read()
                    if err:
                        print("[UWB] Process exited early. Error:\n", err)
                    break
                # No line yet, still running
                time.sleep(0.01)
                continue

            line = line.strip()
            print("[UWB]", line)

            # Look for NLos/Dist/Azimuth/Elevation pattern
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
        print("[UWB] nxp.py process terminated for this cycle.")


def uwb_worker():
    """Background worker: repeatedly run nxp.py in 5-second windows."""
    data_pattern = re.compile(
        r"NLos:(\d+).*Dist:(\d+).*Azimuth:([-\d\.]+).*Elevation:([-\d\.]+)"
    )
    print("[UWB] Background worker started.")
    while not uwb_stop_event.is_set():
        run_uwb_once(data_pattern)
    print("[UWB] Background worker exiting.")


def capture_frame(img_dir: Path, prefix: str, index: int):
    """
    Capture one still image with rpicam-still.
    Returns (filename, timestamp_iso, full_path).
    """
    now = datetime.now()
    ts_iso = now.isoformat(timespec="milliseconds")
    fname = f"{prefix}_{now.strftime('%Y%m%d_%H%M%S_%f')[:-3]}.jpg"
    path = img_dir / fname

    try:
        subprocess.run(
            ["rpicam-still", "-n", "-t", "1", "-o", str(path)],
            check=True,
        )
    except FileNotFoundError:
        raise SystemExit(
            "rpicam-still not found. Install rpicam-apps:\n"
            "  sudo apt install -y rpicam-apps"
        )
    except subprocess.CalledProcessError as e:
        print("[CAM] Error running rpicam-still:", e)
        return None, None, None

    print(f"[CAM] [{index}] -> {fname} @ {ts_iso}")
    return fname, ts_iso, path


def connect_to_server(server_ip, server_port):
    """Create TCP connection to desktop viewer. Returns (sock, file_obj) or (None, None)."""
    if not server_ip:
        print("[NET] No server IP provided, streaming disabled.")
        return None, None

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print(f"[NET] Connecting to {server_ip}:{server_port} ...")
        sock.connect((server_ip, server_port))
        f = sock.makefile("w")  # text mode for JSON lines
        print("[NET] Connected to desktop.")
        return sock, f
    except Exception as e:
        print(f"[NET] Could not connect to {server_ip}:{server_port}: {e}")
        print("[NET] Continuing without streaming.")
        return None, None


def main():
    p = argparse.ArgumentParser(description="Pi node capture + CSV + streaming client")
    p.add_argument("--out", type=Path, required=True, help="Output directory for session")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL,
                   help=f"Seconds between frames (default {DEFAULT_INTERVAL})")
    p.add_argument("--count", type=int, default=DEFAULT_COUNT,
                   help=f"Number of frames to capture (default {DEFAULT_COUNT})")
    p.add_argument("--prefix", default="img", help="Image filename prefix (default 'img')")
    p.add_argument("--node-id", required=True, help="Unique node id (e.g., node1)")
    p.add_argument("--server-ip", default=None, help="Desktop server IP for streaming")
    p.add_argument("--server-port", type=int, default=5000, help="Desktop server port")
    args = p.parse_args()

    # Prepare directories
    outdir: Path = args.out
    img_dir = outdir / "images"
    outdir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)

    csv_path = outdir / "frames.csv"

    print(f"[INFO] Output directory: {outdir.resolve()}")
    print(f"[INFO] Image directory:  {img_dir.resolve()}")
    print(f"[INFO] Will capture {args.count} frames every {args.interval}s")
    print(f"[INFO] Combined CSV:     {csv_path}")
    print(f"[INFO] Node ID:          {args.node_id}")
    print("Press Ctrl+C to stop early.\n")

    # Start IMU
    imu_sensor = get_imu_sensor()

    # Start UWB background thread
    uwb_thread = threading.Thread(target=uwb_worker, daemon=True)
    uwb_thread.start()

    # Connect to desktop (if IP provided)
    sock, sock_file = connect_to_server(args.server_ip, args.server_port)

    # Open combined CSV
    with csv_path.open("w", newline="") as fcsv:
        writer = csv.writer(fcsv)
        writer.writerow([
            "frame_index",
            "img_filename",
            "img_timestamp_iso",
            # IMU
            "imu_timestamp",
            "imu_temp_c",
            "imu_heading_deg",
            "imu_roll_deg",
            "imu_pitch_deg",
            "imu_sys_cal",
            "imu_gyro_cal",
            "imu_accel_cal",
            "imu_mag_cal",
            # UWB
            "uwb_timestamp",
            "uwb_distance_cm",
            "uwb_azimuth_deg",
            "uwb_elevation_deg",
            "uwb_nlos_status",
        ])

        # Use monotonic scheduling to avoid drift
        t_next = time.monotonic()
        try:
            for i in range(1, args.count + 1):
                t_next += args.interval

                # 1) Capture image
                img_fname, img_ts, img_path = capture_frame(img_dir, args.prefix, i)
                if img_fname is None:
                    # camera error; skip this frame
                    continue

                # 2) Read IMU
                imu = read_imu(imu_sensor)

                # 3) Snapshot latest UWB
                with uwb_lock:
                    uwb = uwb_last.copy()

                # 4) Write row to CSV
                row = [
                    i,
                    img_fname,
                    img_ts,

                    imu.get("timestamp"),
                    imu.get("temp_c"),
                    imu.get("heading"),
                    imu.get("roll"),
                    imu.get("pitch"),
                    imu.get("sys_cal"),
                    imu.get("gyro_cal"),
                    imu.get("accel_cal"),
                    imu.get("mag_cal"),

                    uwb.get("timestamp"),
                    uwb.get("distance_cm"),
                    uwb.get("azimuth_deg"),
                    uwb.get("elevation_deg"),
                    uwb.get("nlos"),
                ]
                writer.writerow(row)
                fcsv.flush()

                # 5) Stream to desktop (if connected)
                if sock_file is not None:
                    try:
                        with img_path.open("rb") as fimg:
                            img_bytes = fimg.read()
                        img_b64 = base64.b64encode(img_bytes).decode("ascii")

                        msg = {
                            "node_id": args.node_id,
                            "frame_index": i,
                            "timestamp": img_ts,  # image timestamp
                            "imu": imu,
                            "uwb": uwb,
                            "image_b64": img_b64,
                        }

                        line = json.dumps(msg) + "\n"
                        sock_file.write(line)
                        sock_file.flush()
                        print(f"[SEND] Sent frame {i} from {args.node_id} @ {img_ts}")
                    except Exception as e:
                        print("[NET] Streaming error, disabling streaming:", e)
                        try:
                            sock.close()
                        except Exception:
                            pass
                        sock = None
                        sock_file = None

                # 6) Sleep until next frame
                remaining = t_next - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)

        except KeyboardInterrupt:
            print("\n[INFO] Stopping capture early due to Ctrl+C.")

    # Signal UWB thread to stop and wait for it
    uwb_stop_event.set()
    uwb_thread.join(timeout=2.0)

    if sock is not None:
        try:
            sock.close()
        except Exception:
            pass

    print("[INFO] Done. Combined CSV written to:", csv_path)


if __name__ == "__main__":
    main()
