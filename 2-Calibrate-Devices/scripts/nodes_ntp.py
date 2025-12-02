#!/usr/bin/env python3

import argparse
import base64
import csv
import json
import math
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

# --------------- UWB CONFIG ---------------
UWB_COMMAND = ["python", "-u", "nxp.py", "i", "100", "/dev/ttyUSB0"]
# ------------------------------------------

I2C_ADDRESS = 0x28  # BNO055 default


# ========== GLOBAL UWB STATE ==========
uwb_lock = threading.Lock()
uwb_last = {
    "timestamp": None,
    "distance_cm": None,
    "azimuth_deg": None,
    "elevation_deg": None,
    "nlos": None,
}

uwb_thread_lock = threading.Lock()
uwb_thread = None  # background window runner
# =======================================


def get_imu_sensor():
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        sensor = adafruit_bno055.BNO055_I2C(i2c, address=I2C_ADDRESS)
        print("[IMU] BNO055 initialized.")
        return sensor
    except Exception as e:
        print("[IMU] CRITICAL: cannot init BNO055:", e)
        print("[IMU] IMU data will be None.")
        return None


def read_imu(sensor):
    """Return a dict of IMU values, None/NaN-safe."""
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
        euler = sensor.euler  # (heading, roll, pitch)
        cal_sys, cal_gyro, cal_accel, cal_mag = sensor.calibration_status
        if euler is None:
            h = r = p = None
        else:
            h, r, p = euler
    except Exception as e:
        print("[IMU] read error:", e)
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


def run_uwb_window(window_sec: float):
    """
    Run nxp.py for window_sec seconds in this thread.
    Continuously updates uwb_last with the latest parsed sample.
    """
    print(f"[UWB] Starting window ({window_sec:.1f}s): {' '.join(UWB_COMMAND)}")

    try:
        proc = subprocess.Popen(
            UWB_COMMAND,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        print("[UWB] ERROR: nxp.py not found")
        return

    pattern = re.compile(
        r"NLos:(\d+).*Dist:(\d+).*Azimuth:([-\d\.]+).*Elevation:([-\d\.]+)"
    )
    start = time.time()

    try:
        while True:
            if time.time() - start >= window_sec:
                break

            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    # process ended
                    err = proc.stderr.read()
                    if err:
                        print("[UWB] early exit, stderr:\n", err)
                    break
                time.sleep(0.01)
                continue

            line = line.strip()
            # print("[UWB]", line)  # uncomment for debugging

            m = pattern.search(line)
            if m:
                ts = datetime.now().isoformat(timespec="milliseconds")
                nlos = int(m.group(1))
                dist = float(m.group(2))
                az = float(m.group(3))
                el = float(m.group(4))

                with uwb_lock:
                    uwb_last["timestamp"] = ts
                    uwb_last["distance_cm"] = dist
                    uwb_last["azimuth_deg"] = az
                    uwb_last["elevation_deg"] = el
                    uwb_last["nlos"] = nlos
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=1)
        except Exception:
            pass
        print("[UWB] window finished.")


def trigger_uwb_async(window_sec: float):
    """
    Start a UWB window in the background if none is running.
    Non-blocking for camera/IMU loop.
    """
    global uwb_thread
    with uwb_thread_lock:
        if uwb_thread is not None and uwb_thread.is_alive():
            # already running
            return
        uwb_thread = threading.Thread(
            target=run_uwb_window, args=(window_sec,), daemon=True
        )
        uwb_thread.start()
        print(f"[UWB] triggered background window ({window_sec:.1f}s)")


def imu_change(prev, cur):
    """
    Simple magnitude of change in heading / pitch (deg).
    Returns 0 if missing data.
    """
    if prev is None or cur is None:
        return 0.0

    def safe(val):
        if val is None:
            return None
        try:
            return float(val)
        except Exception:
            return None

    h0 = safe(prev.get("heading"))
    p0 = safe(prev.get("pitch"))
    h1 = safe(cur.get("heading"))
    p1 = safe(cur.get("pitch"))

    if h0 is None or h1 is None or p0 is None or p1 is None:
        return 0.0

    # minimal signed diff for heading
    def angle_diff(a, b):
        d = (a - b + 180.0) % 360.0 - 180.0
        return d

    dh = angle_diff(h1, h0)
    dp = p1 - p0
    return math.sqrt(dh * dh + dp * dp)


def capture_image(img_dir: Path, prefix: str, index: int):
    """
    Capture one JPEG with rpicam-still.
    Returns (filename, timestamp_iso, full_path) or (None, None, None) on error.
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
        print("[CAM] rpicam-still error:", e)
        return None, None, None

    # print(f"[CAM] [{index}] -> {fname} @ {ts_iso}")
    return fname, ts_iso, path


def connect_server(ip, port):
    if not ip:
        print("[NET] No server IP, streaming disabled.")
        return None, None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print(f"[NET] Connecting to {ip}:{port} ...")
        sock.connect((ip, port))
        f = sock.makefile("w")
        print("[NET] Connected to desktop.")
        return sock, f
    except Exception as e:
        print(f"[NET] Could not connect to {ip}:{port}: {e}")
        print("[NET] Continuing without streaming.")
        return None, None


def main():
    ap = argparse.ArgumentParser(
        description="Adaptive Pi node: warm-up UWB+IMU, then fast streaming with IMU-triggered UWB."
    )
    ap.add_argument("--out", type=Path, required=True, help="Output directory")
    ap.add_argument("--node-id", required=True, help="Node id (e.g. node1)")
    ap.add_argument("--server-ip", default=None, help="Desktop IP for streaming")
    ap.add_argument("--server-port", type=int, default=5000)

    ap.add_argument("--slow-interval", type=float, default=1.0,
                    help="Warm-up interval (s) [default 1.0]")
    ap.add_argument("--fast-interval", type=float, default=0.1,
                    help="Post warm-up interval (s) [default 0.1]")
    ap.add_argument("--warmup-frames", type=int, default=15,
                    help="Number of initial frames with guaranteed UWB+IMU [default 15]")
    ap.add_argument("--imu-threshold", type=float, default=3.0,
                    help="IMU change magnitude (deg) to trigger UWB [default 3.0]")
    ap.add_argument("--uwb-window", type=float, default=5.0,
                    help="Duration of each UWB window in seconds [default 5.0]")
    ap.add_argument("--max-frames", type=int, default=0,
                    help="Stop after this many frames (0 = run forever)")
    args = ap.parse_args()

    outdir: Path = args.out
    img_dir = outdir / "images"
    outdir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)

    csv_path = outdir / "frames.csv"

    print(f"[INFO] Output dir:   {outdir.resolve()}")
    print(f"[INFO] Node id:      {args.node_id}")
    print(f"[INFO] Warm-up:      {args.warmup_frames} frames @ {args.slow_interval}s")
    print(f"[INFO] Fast interval:{args.fast_interval}s (≈ {1.0/args.fast_interval:.1f} FPS)")
    print(f"[INFO] IMU thresh:   {args.imu_threshold} deg")
    print(f"[INFO] UWB window:   {args.uwb_window}s")
    print("Press Ctrl+C to stop.\n")

    # IMU
    imu_sensor = get_imu_sensor()
    prev_imu = None

    # Networking
    sock, sock_file = connect_server(args.server_ip, args.server_port)

    # CSV writer
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

        frame_idx = 0

        # warm-up: start a big UWB window that covers warm-up duration
        warmup_window = args.warmup_frames * args.slow_interval + 1.0
        trigger_uwb_async(warmup_window)

        try:
            t_next = time.monotonic()
            while True:
                frame_idx += 1

                # choose interval based on warm-up vs fast phase
                interval = args.slow_interval if frame_idx <= args.warmup_frames else args.fast_interval
                t_next += interval

                # 1) capture image
                img_fname, img_ts, img_path = capture_image(img_dir, args.node_id, frame_idx)
                if img_fname is None:
                    # failed frame, skip but keep schedule
                    continue

                # 2) IMU
                imu = read_imu(imu_sensor)

                # 3) IMU-based UWB trigger (after warm-up)
                change_mag = imu_change(prev_imu, imu)
                if frame_idx > args.warmup_frames and change_mag >= args.imu_threshold:
                    trigger_uwb_async(args.uwb_window)

                prev_imu = imu

                # 4) snapshot latest UWB
                with uwb_lock:
                    uwb = uwb_last.copy()

                # 5) log to CSV
                row = [
                    frame_idx,
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

                # 6) stream to desktop
                if sock_file is not None:
                    try:
                        with img_path.open("rb") as fimg:
                            img_bytes = fimg.read()
                        img_b64 = base64.b64encode(img_bytes).decode("ascii")
                        msg = {
                            "node_id": args.node_id,
                            "frame_index": frame_idx,
                            "timestamp": img_ts,  # NTP-synced wall time
                            "imu": imu,
                            "uwb": uwb,
                            "image_b64": img_b64,
                        }
                        sock_file.write(json.dumps(msg) + "\n")
                        sock_file.flush()
                    except Exception as e:
                        print("[NET] streaming error, disabling:", e)
                        try:
                            sock.close()
                        except Exception:
                            pass
                        sock = None
                        sock_file = None

                # 7) stop condition?
                if args.max_frames > 0 and frame_idx >= args.max_frames:
                    print("[INFO] Reached max_frames, exiting.")
                    break

                # 8) wait until next tick
                remaining = t_next - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)

        except KeyboardInterrupt:
            print("\n[INFO] Ctrl+C, stopping.")

    if sock is not None:
        try:
            sock.close()
        except Exception:
            pass

    print("[INFO] CSV written to", csv_path)


if __name__ == "__main__":
    main()
