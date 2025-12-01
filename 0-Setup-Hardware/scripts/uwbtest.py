import subprocess
import csv
import re
import time
from datetime import datetime

# =================CONFIGURATION=================
UWB_COMMAND = ["python", "-u", "nxp.py", "i", "100", "/dev/ttyUSB0"]  # Change port if needed
OUTPUT_FILE = "uwb_data.csv"
RUN_WINDOW_SEC = 5  # run nxp.py for 5 seconds each cycle
# ===============================================


def run_uwb_once(writer, data_pattern, csv_file):
    """
    Run nxp.py once for RUN_WINDOW_SEC seconds,
    log any parsed lines to CSV, then stop.
    """
    print(f"\n[+] Starting UWB script: {' '.join(UWB_COMMAND)}")
    process = subprocess.Popen(
        UWB_COMMAND,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1  # line-buffered
    )

    start_time = time.time()

    try:
        while True:
            # Stop after RUN_WINDOW_SEC seconds
            if time.time() - start_time >= RUN_WINDOW_SEC:
                print(f"[i] {RUN_WINDOW_SEC}s window elapsed, restarting nxp.py...")
                break

            line = process.stdout.readline()

            # If the process has exited and there's no more output
            if not line:
                if process.poll() is not None:
                    print("[!] nxp.py exited before time window finished.")
                    err = process.stderr.read()
                    if err:
                        print("Error details:\n", err)
                    break
                # No line yet but still running — avoid busy spinning
                time.sleep(0.01)
                continue

            # Show raw output
            print(line.strip())

            # Parse line using regex
            match = data_pattern.search(line)
            if match:
                timestamp = datetime.now().strftime("%H:%M:%S.%f")
                nlos = match.group(1)      # Non-Line-of-Sight flag
                dist = match.group(2)      # Distance in cm
                azimuth = match.group(3)   # Angle
                elevation = match.group(4) # Height angle

                # Write to CSV and flush
                writer.writerow([timestamp, dist, azimuth, elevation, nlos])
                csv_file.flush()

    finally:
        # Ensure the process is stopped at the end of this window
        try:
            process.terminate()
        except Exception:
            pass
        try:
            process.wait(timeout=1)
        except Exception:
            pass
        print("[i] nxp.py process terminated for this cycle.")


def log_uwb_data():
    print(f"Logging data to: {OUTPUT_FILE}")
    print("Press Ctrl+C to stop logging.\n")

    # Compile regex once
    data_pattern = re.compile(
        r"NLos:(\d+).*Dist:(\d+).*Azimuth:([-\d\.]+).*Elevation:([-\d\.]+)"
    )

    # Open the CSV file once and keep reusing it
    with open(OUTPUT_FILE, mode='w', newline='') as csv_file:
        writer = csv.writer(csv_file)
        # Header columns
        writer.writerow(["Timestamp", "Distance_cm", "Azimuth_deg", "Elevation_deg", "NLoS_Status"])

        try:
            # Continuous cycles: each cycle runs nxp.py for RUN_WINDOW_SEC seconds
            while True:
                run_uwb_once(writer, data_pattern, csv_file)
        except KeyboardInterrupt:
            print("\n[!] Stopping logger...")


if __name__ == "__main__":
    log_uwb_data()
