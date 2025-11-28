# Stream4D-Pi-Array

**An array of Raspberry Pi 5 nodes with RGB cameras, UWB, and IMU, designed to calibrate relative localization and stream synchronized timestamped data.**

---

## 📖 Overview

This repository contains experiments and scripts for synchronized multi-node sensing on the Raspberry Pi 5. The goal is to capture and stream time-stamped sensor data suitable for multi-view fusion, localization, and 4D reconstruction.



### Key Features
* **RGB Video:** High-quality streaming via **Picamera3**.
* **Inertial Measurement:** 9-DOF data via **BNO055**.
* **Ranging:** Ultra-wideband (UWB) ranging using **Murata LBUA0VG2BP-EVK-P**.
* **Environment:** Ubuntu 25.10 + Python 3.12.

---

## 🛠 Hardware Requirements

### Compute Node
* **Raspberry Pi 5** (8 GB RAM recommended)

### Sensors
* **Camera:** Raspberry Pi Camera Module 3 (Picamera3)
* **IMU:** Bosch BNO055 (Absolute Orientation Sensor)
* **UWB:** Murata UWB Antenna (LBUA0VG2BP-EVK-P)

---

## 💻 Software Prerequisites

* **OS:** Ubuntu 25.10 (64-bit, Raspberry Pi)
* **Python:** Version 3.12 (Strict requirement for all virtual environments)
* **Camera Stack:** `rpicam-apps`, `libcamera`
* **Streaming:** `GStreamer`, `FFmpeg`
* **Build Tools:** `git`, `python3-venv`, `python3-pip`

---

## 🚀 Installation Guide

### 1. Firmware & System Update
Run the following on **each** Raspberry Pi 5 node to ensure the firmware and OS are up to date.

```bash
sudo apt update
sudo apt full-upgrade -y

# Update EEPROM
sudo apt install -y rpi-eeprom
sudo rpi-eeprom-update -a

# Reboot is required
sudo reboot
```