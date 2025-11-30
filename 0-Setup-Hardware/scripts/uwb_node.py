import sys
import serial
import time
import queue
import math
import csv
from threading import Thread, Event
from datetime import datetime

# --- CONFIGURATION ---
SERIAL_PORT = "/dev/ttyUSB0"  # Check your port!
BAUD_RATE = 115200
LOG_FILE = "uwb_data.csv"

# --- GLOBAL VARIABLES ---
command_queue = queue.Queue()
stop_threads = False
role = "Initiator"
receiver_id = 1  # Default ID (only used if role is Responder)
session_active = Event()

# --- UWB COMMANDS (From NXP Documentation) ---
SESSION_ID = [0x57, 0x04, 0x00, 0x00] 
UWB_RESET = [0x20, 0x00, 0x00, 0x01, 0x00]
UWB_SESSION_INIT = [0x21, 0x00, 0x00, 0x05] + SESSION_ID + [0x00]
UWB_RANGE_START = [0x22, 0x00, 0x00, 0x04] + SESSION_ID

# Basic Config (simplified from original for stability)
UWB_CORE_CONFIG = [0x20, 0x04, 0x00, 0x08, 0x01, 0xE4, 0x02, 0x01, 0x00] # Minimal config example

def calculate_location(distance_cm, azimuth_deg, elevation_deg):
    """Converts spherical coordinates to Cartesian (X, Y, Z)"""
    # Convert to meters
    dist_m = distance_cm / 100.0
    
    # Convert degrees to radians
    az_rad = math.radians(azimuth_deg)
    el_rad = math.radians(elevation_deg)
    
    # Calculate Cartesian coordinates
    # Note: Alignment depends on physical board orientation. 
    # Assuming standard mathematical spherical coords:
    x = dist_m * math.cos(el_rad) * math.cos(az_rad)
    y = dist_m * math.cos(el_rad) * math.sin(az_rad)
    z = dist_m * math.sin(el_rad)
    
    return x, y, z

def get_session_config(role, node_id):
    """Generates the specific MAC address config based on Role and ID"""
    # Initiator always has MAC 0x0000. 
    # Responders have MAC based on their node_id (e.g., 1 -> 0x0001)
    
    my_mac = [0x00, 0x00]
    dst_mac = [0x00, 0x00]
    
    if role == "Initiator":
        my_mac = [0x00, 0x00]
        dst_mac = [0xFF, 0xFF] # Broadcast or cycle through specific MACs logic needed here for multi-node
        dev_role = 0x01 # Controller
    else:
        # Responder
        # Convert node_id to 2-byte MAC (Little Endian)
        my_mac = [node_id & 0xFF, (node_id >> 8) & 0xFF]
        dst_mac = [0x00, 0x00] # Respond to Initiator (0x0000)
        dev_role = 0x00 # Controlee

    # Construct the Set App Config Command
    # 0x21 (Session Control), 0x03 (Set App Config)
    cmd = [0x21, 0x03, 0x00, 0x13] + SESSION_ID + [
        0x04, # Number of Params
        0x00, 0x01, dev_role,        # DEVICE_TYPE
        0x06, 0x02, my_mac[0], my_mac[1], # DEVICE_MAC_ADDRESS
        0x07, 0x02, dst_mac[0], dst_mac[1], # DST_MAC_ADDRESS
        0x11, 0x01, (1 if role == "Initiator" else 0) # ROLE
    ]
    return cmd

def serial_writer(ser):
    while not stop_threads:
        try:
            cmd = command_queue.get(timeout=1)
            # Add header and checksum if needed by specific firmware version, 
            # usually raw bytes are sent for NXP UCI.
            packet = bytearray(cmd)
            ser.write(packet)
            # print(f"Sent: {packet.hex()}")
            time.sleep(0.1) # Small delay for stability
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Serial Write Error: {e}")

def serial_reader(ser, csv_writer):
    print("Listening for UWB Data...")
    while not stop_threads:
        if ser.in_waiting > 0:
            # Read header first (4 bytes standard UCI)
            header = ser.read(4)
            if len(header) < 4: continue
            
            # Parse payload length
            payload_len = header[3]
            payload = ser.read(payload_len)
            
            # Check if this is a Range Notification (0x62 0x00 ...)
            if header[0] == 0x62 and header[1] == 0x00:
                parse_ranging_data(payload, csv_writer)

def parse_ranging_data(payload, csv_writer):
    # This parsing logic follows the NXP UCI structure from your original file
    # Payload offsets based on 'nxp.py' extract functions
    try:
        # Extract raw bytes (Little Endian)
        seq_id = int.from_bytes(payload[0:4], 'little')
        dist_cm = int.from_bytes(payload[29:31], 'little')
        azimuth_deg = int.from_bytes(payload[31:33], 'little')
        # Handle negative angles (2's complement for 16-bit)
        if azimuth_deg > 32767: azimuth_deg -= 65536
        
        elevation_deg = int.from_bytes(payload[34:36], 'little')
        if elevation_deg > 32767: elevation_deg -= 65536
        
        # Calculate XYZ
        x, y, z = calculate_location(dist_cm, azimuth_deg, elevation_deg)
        
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        print(f"[{timestamp}] ID:{seq_id} | Dist: {dist_cm}cm | Az: {azimuth_deg}° | El: {elevation_deg}°")
        print(f"      Loc -> X: {x:.2f}m, Y: {y:.2f}m, Z: {z:.2f}m")
        print("-" * 40)
        
        # Save to CSV
        if csv_writer:
            csv_writer.writerow([timestamp, seq_id, dist_cm, azimuth_deg, elevation_deg, x, y, z])
            
    except Exception as e:
        print(f"Parse Error: {e}")

def main():
    global role, receiver_id, stop_threads
    
    # Parse Arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == 'r':
            role = "Responder"
            if len(sys.argv) > 2:
                receiver_id = int(sys.argv[2])
            print(f"Starting as RESPONDER (ID: {receiver_id})...")
        else:
            role = "Initiator"
            print("Starting as INITIATOR...")
    else:
        print("Usage: python3 uwb_node.py [i|r] [receiver_id]")
        print("Defaulting to Initiator...")

    # Setup Serial
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
    except Exception as e:
        print(f"Could not open serial port {SERIAL_PORT}: {e}")
        return

    # Open CSV
    f = open(LOG_FILE, 'w', newline='') 
    writer = csv.writer(f)
    writer.writerow(["Timestamp", "SeqID", "Distance_cm", "Azimuth_deg", "Elevation_deg", "X_m", "Y_m", "Z_m"])

    # Start Threads
    t_read = Thread(target=serial_reader, args=(ser, writer))
    t_write = Thread(target=serial_writer, args=(ser,))
    t_read.start()
    t_write.start()

    # Initialization Sequence
    print("Initializing UWB Session...")
    command_queue.put(UWB_RESET)
    time.sleep(0.5)
    command_queue.put(UWB_SESSION_INIT)
    time.sleep(0.1)
    
    # Set Role/Mac Config
    config_cmd = get_session_config(role, receiver_id)
    command_queue.put(config_cmd)
    time.sleep(0.1)
    
    # Start Ranging
    command_queue.put(UWB_RANGE_START)
    print("Ranging Started. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        stop_threads = True
        t_read.join()
        t_write.join()
        ser.close()
        f.close()
        print("Done.")

if __name__ == "__main__":
    main()