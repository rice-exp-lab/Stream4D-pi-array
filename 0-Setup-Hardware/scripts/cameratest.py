#!/usr/bin/env python3
"""
Minimal timestamped still-image capture for Raspberry Pi Camera (Pi 5 + Cam v3).
- Saves JPEGs into a folder
- Writes a CSV with: filename,timestamp_iso
- Uses rpicam-still (libcamera) via subprocess for simplicity

Usage examples
  python3 simple_timed_capture.py --out shots --interval 2 --count 50
  python3 simple_timed_capture.py --out shots   # default: interval=1s, count=10
"""
import argparse
import csv
import subprocess
import time
from datetime import datetime
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description="Simple interval capture with CSV log")
    p.add_argument("--out", type=Path, required=True, help="Output directory")
    p.add_argument("--interval", type=float, default=1.0, help="Seconds between shots (default 1.0)")
    p.add_argument("--count", type=int, default=10, help="How many images to capture (default 10)")
    p.add_argument("--prefix", default="img", help="Filename prefix (default 'img')")
    args = p.parse_args()

    outdir: Path = args.out
    outdir.mkdir(parents=True, exist_ok=True)
    csv_path = outdir / "shots.csv"

    # Open CSV and write header
    with csv_path.open("w", newline="") as fcsv:
        writer = csv.writer(fcsv)
        writer.writerow(["filename", "timestamp_iso"])  # header

        print(f"Saving {args.count} images to {outdir.resolve()} (every {args.interval}s)")

        # Use monotonic scheduling to avoid drift
        t_next = time.monotonic()
        for i in range(args.count):
            t_next += args.interval

            # Timestamp for filename and CSV
            now = datetime.now()
            ts_iso = now.isoformat(timespec="milliseconds")
            fname = f"{args.prefix}_{now.strftime('%Y%m%d_%H%M%S_%f')[:-3]}.jpg"
            path = outdir / fname

            # Capture one still (requires rpicam-still in PATH)
            # -n = no preview, -t 1 = minimal timeout, -o file
            try:
                subprocess.run([
                    "rpicam-still", "-n", "-t", "1", "-o", str(path)
                ], check=True)
            except FileNotFoundError:
                raise SystemExit("rpicam-still not found. Install rpicam-apps: sudo apt install -y rpicam-apps")

            # Log to CSV
            writer.writerow([fname, ts_iso])
            fcsv.flush()
            print(f"[{i+1}/{args.count}] -> {fname} @ {ts_iso}")

            # Sleep until next tick (avoid negative)
            remaining = t_next - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)

    print(f"Done. Wrote CSV: {csv_path}")


if __name__ == "__main__":
    main()
