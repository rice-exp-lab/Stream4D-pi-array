import time
import board
import busio
import csv
import adafruit_bno055

# --- CONFIGURATION ---
OUTPUT_FILE = "imu_data.csv"
I2C_ADDRESS = 0x28  # Change to 0x29 if you get a connection error

def get_sensor():
    """Initializes the sensor safely."""
    try:
        # Initialize I2C connection
        i2c = busio.I2C(board.SCL, board.SDA)
        sensor = adafruit_bno055.BNO055_I2C(i2c, address=I2C_ADDRESS)
        return sensor
    except Exception as e:
        print(f"\nCRITICAL ERROR: Could not connect to sensor.")
        print(f"Error Details: {e}")
        print("1. Check wiring.")
        print("2. Ensure 'dtparam=i2c_arm_baudrate=10000' is in /boot/firmware/config.txt")
        return None

def main():
    sensor = get_sensor()
    if not sensor:
        return

    print(f"Logging data to {OUTPUT_FILE}...")
    print("Move the sensor in a figure-8 to calibrate.")
    print("Press Ctrl+C to stop.")
    print("-" * 60)

    # Open CSV file for writing
    with open(OUTPUT_FILE, mode='w', newline='') as file:
        writer = csv.writer(file)
        # Write the Header Row
        writer.writerow(["Timestamp", "Temp_C", "Heading", "Roll", "Pitch", "Sys_Cal", "Gyro_Cal", "Accel_Cal", "Mag_Cal"])

        while True:
            try:
                # Read Sensor Data
                temp = sensor.temperature
                euler = sensor.euler  # (Heading, Roll, Pitch)
                cal_sys, cal_gyro, cal_accel, cal_mag = sensor.calibration_status
                
                # Get current time
                timestamp = time.strftime("%H:%M:%S")

                # If euler gives None (sensor glitch), use placeholders
                h, r, p = euler if euler else (0, 0, 0)

                # Print to Screen
                print(f"[{timestamp}] Temp: {temp}°C | H: {h:.2f} R: {r:.2f} P: {p:.2f} | Cal: {sensor.calibration_status}")

                # Save to File
                writer.writerow([timestamp, temp, h, r, p, cal_sys, cal_gyro, cal_accel, cal_mag])
                
                # Flush ensures data is saved even if you crash
                file.flush()

                time.sleep(0.2) # Read 5 times a second

            except OSError:
                print("Clock stretching error... retrying")
                time.sleep(0.5)
            except KeyboardInterrupt:
                print("\nStopped by user.")
                break

if __name__ == "__main__":
    main()