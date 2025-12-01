#!/usr/bin/env python3
"""
check_setup.py

Combined capture script for:
- Camera (still images via rpicam-still)
- IMU (BNO055 over I2C)
- UWB (NXP script output parsed from stdout)

Per-frame, we log:
    frame_index,
    image_filename,
    frame_ts_iso,
    IMU fields,
    UWB fields (latest seen).

If IMU or UWB are unavailable or not streaming, rows are still written with
empty fields for that sensor.

Usage example:
    python3 check_setup.py --out run1 --interval 0.2 --count 300 --prefix frame

Dependencies:
    - rpicam-apps (for rpicam-still)
    - Adafruit_BNO055 + Blinka stack for IMU
    - Your nxp.py UWB script in the same directory (or adjust UWB_COMMAND)
"""

import argparse
import csv
import subprocess
import time
import threading
import re
from datetime import datetime
from pathlib import Path

# ------------------ IMU IMPORTS (LAZY-FRIENDLY) ------------------ #
try:
    import board
    import busio
    import adafruit_bno055
    HAS_IMU_LIBS = True
except ImportError as e:
    print("IMU libraries not available, IMU will be disabled:", e)
    HAS_IMU_LIBS = False
    board = busio = adafruit_bno055 = None

# ------------------ IMU CONFIG ------------------ #
IMU_I2C_ADDRESS = 0x28  # Change to 0x29 if needed


def get_imu_sensor():
    """Try to create the BNO055 IMU sensor. Returns None on failure."""
    if not HAS_IMU_LIBS:
        return None
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        sensor = adafruit_bno055.BNO055_I2C(i2c, address=IMU_I2C_ADDRESS)
        print("IMU: BNO055 connected.")
        return sensor
    except Exception as e:
        print("\nIMU ERROR: Could not connect to BNO055.")
        print("  Details:", e)
        print("  (Check wiring and I2C config.)")
        return None


def read_imu(sensor):
    """
    Read one IMU sample.
    Returns a dict:
        {
            "temp": float or None,
            "heading": float or None,
            "roll": float or None,
            "pitch": float or None,
            "sys_cal": int or None,
            "gyro_cal": int or None,
            "accel_cal": int or None,
            "mag_cal": int or None,
        }
    If sensor is None or reading fails, all fields are None.
    """
    empty = {
        "temp": None,
        "heading": None,
        "roll": None,
        "pitch": None,
        "sys_cal": None,
        "gyro_cal": None,
        "accel_cal": None,
        "mag_cal": None,
    }
    if sensor is None:
        return empty

    try:
        temp = sensor.temperature
        euler = sensor.euler  # (heading, roll, pitch) or None
        if euler:
            h, r, p = euler
        else:
            h, r, p = (None, None, None)
        cal_sys, cal_gyro, cal_accel, cal_mag = sensor.calibration_status
        return {
            "temp": temp,
            "heading": h,
            "roll": r,
            "pitch": p,
            "sys_cal": cal_sys,
            "gyro_cal": cal_gyro,
            "accel_cal": cal_accel,
            "mag_cal": cal_mag,
        }
    except Exception as e:
        print("IMU read error:", e)
        return empty


# ------------------ UWB CONFIG ------------------ #
# This should match the command you use to run your UWB script.
# Adjust as needed (device path, args, etc.).
UWB_COMMAND = ["python", "-u", "nxp.py", "i", "100", "/dev/ttyUSB0"]

# Regex to extract NLoS, distance, azimuth, elevation from nxp.py output
UWB_PATTERN = re.compile(
    r"NLos:(\d+).*Dist:(\d+).*Azimuth:([-\d\.]+).*Elevation:([-\d\.]+)"
)


class UWBReader(threading.Thread):
    """
    Background thread that runs the UWB script and keeps the latest parsed
    reading in memory.
    """

    def __init__(self):
        super().__init__(daemon=True)
        self.latest = None  # dict or None
        self.lock = threading.Lock()
        self._stop_event = threading.Event()
        self.process = None

    def run(self):
        print("Starting UWB subprocess:", " ".join(UWB_COMMAND))
        try:
            self.process = subprocess.Popen(
                UWB_COMMAND,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except Exception as e:
            print("ERROR: Could not start UWB process:", e)
            return

        try:
            while not self._stop_event.is_set():
                line = self.process.stdout.readline()
                if not line and self.process.poll() is not None:
                    # Process ended
                    print("UWB subprocess has stopped.")
                    err = self.process.stderr.read()
                    if err:
                        print("UWB error details:\n", err)
                    break

                if not line:
                    # No data; small sleep to avoid tight loop
                    time.sleep(0.01)
                    continue

                line = line.strip()
                # Optional: print raw line for debugging
                # print("[UWB]", line)

                m = UWB_PATTERN.search(line)
                if m:
                    timestamp = datetime.now().strftime("%H:%M:%S.%f")
                    nlos = m.group(1)
                    dist = m.group(2)
                    azimuth = m.group(3)
                    elevation = m.group(4)
                    with self.lock:
                        self.latest = {
                            "timestamp": timestamp,
                            "distance_cm": dist,
                            "azimuth_deg": azimuth,
                            "elevation_deg": elevation,
                            "nlos_status": nlos,
                        }
        finally:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
            print("UWBReader thread exiting.")

    def stop(self):
        self._stop_event.set()

    def get_latest(self):
        """Return a shallow copy of the latest UWB reading or None."""
        with self.lock:
            if self.latest is None:
                return None
            return dict(self.latest)


# ------------------ CAMERA CAPTURE ------------------ #
def capture_frame(out_path: Path):
    """
    Capture one JPEG still using rpicam-still.
    Raises SystemExit if rpicam-still is missing.
    """
    try:
        subprocess.run(
            ["rpicam-still", "-n", "-t", "1", "-o", str(out_path)],
            check=True,
        )
    except FileNotFoundError:
        raise SystemExit(
            "rpicam-still not found. Install with:\n"
            "  sudo apt install -y rpicam-apps"
        )
    except subprocess.CalledProcessError as e:
        print("Camera capture error:", e)


# ------------------ MAIN LOOP ------------------ #
def main():
    parser = argparse.ArgumentParser(
        description="Combined camera + IMU + UWB per-frame capture"
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output directory for images and CSV",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Seconds between frames (default: 1.0)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of frames to capture (default: 10)",
    )
    parser.add_argument(
        "--prefix",
        default="frame",
        help="Image filename prefix (default: 'frame')",
    )

    args = parser.parse_args()
    outdir: Path = args.out
    outdir.mkdir(parents=True, exist_ok=True)

    csv_path = outdir / "combined_log.csv"

    # Init IMU
    imu_sensor = get_imu_sensor()
    if imu_sensor is None:
        print("IMU disabled: will log empty IMU fields.")

    # Init UWB reader
    uwb_reader = UWBReader()
    uwb_reader.start()
    print("UWB reader started (if UWB is connected and nxp.py is working).")

    # Prepare CSV
    with csv_path.open("w", newline="") as fcsv:
        writer = csv.writer(fcsv)

        # Header
        writer.writerow(
            [
                "frame_index",
                "image_filename",
                "frame_ts_iso",
                # IMU fields
                "imu_temp_C",
                "imu_heading_deg",
                "imu_roll_deg",
                "imu_pitch_deg",
                "imu_sys_cal",
                "imu_gyro_cal",
                "imu_accel_cal",
                "imu_mag_cal",
                # UWB fields
                "uwb_sample_ts",
                "uwb_distance_cm",
                "uwb_azimuth_deg",
                "uwb_elevation_deg",
                "uwb_nlos_status",
            ]
        )

        print(
            f"Capturing {args.count} frames to {outdir.resolve()} "
            f"(every {args.interval}s)"
        )

        t_next = time.monotonic()
        for i in range(args.count):
            t_next += args.interval

            # Timestamp for this frame
            now = datetime.now()
            frame_ts_iso = now.isoformat(timespec="milliseconds")
            fname = f"{args.prefix}_{now.strftime('%Y%m%d_%H%M%S_%f')[:-3]}.jpg"
            img_path = outdir / fname

            # --- Capture image ---
            capture_frame(img_path)

            # --- Read IMU (if available) ---
            imu_data = read_imu(imu_sensor)

            # --- Grab latest UWB sample (if any) ---
            uwb_sample = uwb_reader.get_latest() or {
                "timestamp": None,
                "distance_cm": None,
                "azimuth_deg": None,
                "elevation_deg": None,
                "nlos_status": None,
            }

            # --- Write CSV row ---
            writer.writerow(
                [
                    i,
                    fname,
                    frame_ts_iso,
                    # IMU
                    imu_data["temp"],
                    imu_data["heading"],
                    imu_data["roll"],
                    imu_data["pitch"],
                    imu_data["sys_cal"],
                    imu_data["gyro_cal"],
                    imu_data["accel_cal"],
                    imu_data["mag_cal"],
                    # UWB
                    uwb_sample["timestamp"],
                    uwb_sample["distance_cm"],
                    uwb_sample["azimuth_deg"],
                    uwb_sample["elevation_deg"],
                    uwb_sample["nlos_status"],
                ]
            )
            fcsv.flush()

            print(
                f"[{i+1}/{args.count}] {fname} @ {frame_ts_iso} | "
                f"IMU: H={imu_data['heading']} R={imu_data['roll']} P={imu_data['pitch']} | "
                f"UWB dist={uwb_sample['distance_cm']}cm"
            )

            # Wait for next frame time
            remaining = t_next - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)

    # Stop UWB reader
    uwb_reader.stop()
    uwb_reader.join(timeout=2.0)

    print("Done.")
    print("Images directory:", outdir.resolve())
    print("Combined CSV:", csv_path.resolve())


if __name__ == "__main__":
    main()
