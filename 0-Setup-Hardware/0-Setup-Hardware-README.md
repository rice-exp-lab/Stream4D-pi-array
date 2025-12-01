# Stream4D-Pi-Array

**An array of Raspberry Pi 5 nodes with RGB cameras, UWB, and IMU, designed to calibrate relative localization and stream synchronized timestamped data.**

---

## 📖 Overview

This repository contains experiments and scripts for synchronized multi-node sensing on the Raspberry Pi 5. The goal is to capture and stream time-stamped sensor data suitable for multi-view fusion, localization, and 4D reconstruction.

### Key Features
- **RGB Video:** High-quality streaming via Picamera3.
- **Inertial Measurement:** 9-DOF data via BNO055.
- **Ranging:** Ultra-wideband (UWB) ranging using Murata LBUA0VG2BP-EVK-P.
- **Environment:** Ubuntu 25.10 + Python 3.12.

---

## 🛠 Hardware Requirements

### Compute Node
- Raspberry Pi 5 (8 GB RAM recommended)

### Sensors
- Camera: Raspberry Pi Camera Module 3 (Picamera3)
- IMU: Bosch BNO055 (Absolute Orientation Sensor)
- UWB: Murata UWB Antenna (LBUA0VG2BP-EVK-P)

---

## 💻 Software Prerequisites

- OS: Ubuntu 25.10 (64-bit, Raspberry Pi)
- Python: Version 3.12 (Strict requirement for all virtual environments)
- Camera Stack: `rpicam-apps`, `libcamera`
- Streaming: `GStreamer`, `FFmpeg`
- Build Tools: `git`, `python3-venv`, `python3-pip`

---

## 🚀 Installation Guide

### 1. Firmware & System Update
Run the following on **each** Raspberry Pi 5 node to ensure the firmware and OS are up to date.

Copyable commands (run as a user with sudo):
```bash
# Copyable: system update + firmware
sudo apt update
sudo apt full-upgrade -y

# Install EEPROM updater and apply latest firmware
sudo apt install -y rpi-eeprom
sudo rpi-eeprom-update -a

# Reboot to apply firmware updates
sudo reboot
```
# Camera Streaming Libraries + UWB and IMU libraries
sudo apt install -y rpicam-apps libcamera-tools \
  gstreamer1.0-libcamera gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly ffmpeg

 sudo apt install -y   git build-essential cmake   libopenblas-dev libjpeg-dev gfortran   libzmq3-dev libgpiod-dev   i2c-tools libi2c-dev   python3-dev python3-pip python3-venv


sudo usermod -aG video,render,dialout,i2c,gpio $USER

newgrp video
rpicam-hello --list-cameras


sudo apt update
sudo apt install -y i2c-tools python3-pip python3-smbus
sudo i2cdetect -y 1

sudo apt install -y python3-lgpio liblgpio1
sudo apt-get install python3-picamera

python3 -m venv dcc
source dcc/bin/activate


pip install adafruit-blinka adafruit-circuitpython-bno055

pip install pyserial numpy pyzmq pandas opencv-python

