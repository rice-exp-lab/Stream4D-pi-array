from ucitool import UciDevice

# Connect to the Murata/NXP UWB Module via UART
uwb = UciDevice(port='/dev/ttyUSB3', baudrate=115200) # Adjust port as needed

# Initialize Session (Conceptual - actual commands depend on FiRa spec)
uwb.send_command("SESSION_INIT", session_id=1)
uwb.send_command("RANGE_START", session_id=1)

# Read Loop
while True:
    packet = uwb.read_packet()
    if packet.type == "RANGE_DATA":
        print(f"Distance: {packet.distance_cm} cm")
        # You can pipe this data into the 3D visualization script I provided earlier