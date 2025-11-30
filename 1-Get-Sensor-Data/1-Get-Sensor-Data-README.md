# Get Sensor Data

This step describes how the Pi nodes initialize, join the array network, and validate attached sensors (camera, IMU, UWB). It explains roles, test procedures, and how to run the validation utility.

## Overview
- The first Pi that starts the network becomes the *master* and holds network priority.
- Subsequent Pis join as *subordinate* nodes.
- If the master goes offline, leadership is reassigned to the next connected node.

## Goals
- Confirm each node has required peripherals (camera, BNO055 IMU, Murata UWB).
- Verify data streams are producing timestamps and values in the expected order.
- Produce a node validation log for debugging and inventory.

## Prerequisites
- Refer to the main project setup: [README.md](../README.md) and hardware setup: [0-Setup-Hardware/0-Setup-Hardware-README.md](../0-Setup-Hardware/0-Setup-Hardware-README.md).
- Each Pi should have networking configured and Python 3.12 virtual environment active.

## Validation tool
Use the validation script to collect a quick diagnostic of devices and streams:

- Script: [1-Get-Sensor-Data/scripts/validate_nodes.py](scripts/validate_nodes.py)
- Purpose: Detect attached peripherals, sample a few frames/sensor packets, log timestamps and basic sanity checks.

Example usage:
```sh
# Activate venv, then on each node (or via orchestrator)
python3 scripts/validate_nodes.py --sample 10 --output validate_log.json
```

## Expected output
- A JSON or plain-text log that lists nodes, detected devices, sample timestamps, and any warnings or errors.
- Summary indicating overall health and which devices (if any) failed validation.

## Troubleshooting
- No camera: verify libcamera and Picamera3 installation and camera ribbon connection.
- IMU/UWB missing: check I2C/UART configs and kernel modules.
- Network/leader problems: ensure correct startup order and stable LAN; check logs on the master node.

## Next steps
- Once validation passes, proceed to data capture and synchronization routines in the scripts folder - [2-Calibrate-Devices/scripts/](2-Calibrate-Devices/scripts/) .
- If you need to update hardware steps, see [0-Setup-Hardware/0-Setup-Hardware-README.md](../0-Setup-Hardware/0-Setup-Hardware-README.md).