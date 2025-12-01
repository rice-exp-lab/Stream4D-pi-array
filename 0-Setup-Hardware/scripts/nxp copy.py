# /*====================================================================================*/
# /*                                                                                    */
# /*                        Copyright 2021 NXP                                          */
# /*                                                                                    */
# /*   All rights are reserved. Reproduction in whole or in part is prohibited          */
# /*   without the written consent of the copyright owner.                              */
# /*                                                                                    */
# /*   NXP reserves the right to make changes without notice at any time. NXP makes     */
# /*   no warranty, expressed, implied or statutory, including but not limited to any   */
# /*   implied warranty of merchantability or fitness for any particular purpose,       */
# /*   or that the use will not infringe any third party patent, copyright or trademark.*/
# /*   NXP must not be liable for any loss or damage arising from its use.              */
# /*                                                                                    */
# /*====================================================================================*/

from datetime import datetime
from threading import Thread, Condition, Event

import numpy as np
import os
import queue
import serial
import signal
import sys
import zmq
import time

# Arguments: DS-TWR_Unicast.py [i|r] [COM12] [10] [notime] [noplot|nocirplot] [ipc <prefix_file_name> | <bin_path>]
#   Role of the Rhodes board ("i" for initiator, "r" for responder)
#   Communication Port (e.g. "COM12")
#   Number of valid measurements before stop session (no stop if missing or 0)
#   Don't put date and time in the log
#   "noplot" to not display all the plots or "nocirplot" to display plots of distance and AoA but nor CIR amplitude
#   "ipc" to store all output into file which name is controled by IPC (in this case, timestamp and plots are disabled)
#   or bin_path to store CIR, RFrame and Range Data notifications in binary files (no store if empty)


# Default role of the Rhodes board (Initiator|Responder)
rhodes_role = "Initiator"

# Default Port value (COMxx)
com_port = "/dev/ttyUSB0"

# Number of valid measurement before stop (0: no stop)
nb_meas = 0

# To add date and time in the log
is_timestamp = True

# To display plot of range data
is_range_plot = True

# To display plot of rframe data
is_cir_plot = True

# To control the name of output log by IPC
is_ipc = False

# Prefixe of output files in IPC mode
prefix_ipc = ""

# added on 2021.07.15
channel_ID = [0x09]

# Initialize the UWBD for specific platform variant
# UWB_SET_BOARD_VARIANT = [0x2E, 0x00, 0x00, 0x02, 0x73, 0x02]
UWB_SET_BOARD_VARIANT = [0x2E, 0x00, 0x00, 0x02, 0x2A, 0x03]

# Reset the UWB device
UWB_RESET_DEVICE = [0x20, 0x00, 0x00, 0x01, 0x00]

# Configure parameters of the UWB device
UWB_CORE_SET_CONFIG = [0x20, 0x04, 0x00, 0xAA,
                       0x08,  # Number of parameters
                       0x01, 0x01, 0x01,  # LOW_POWER_MODE
                       0xE4, 0x00, 0x08,  # DELAY_CALIBRATION_VALUE
                       0x05, 0x3B,  # Channel 5 add delay 8/18 by kato
                       0x10, 0x3B,  # Channel 6
                       0x10, 0x3B,  # Channel 8
                       0xE9, 0x3A,  # Channel 9 add delay 8/18 by kato
                       0xE4, 0x01, 0x80,  # AOA_CALIBRATION_CTRL
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 1 Channel 5
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 2 Channel 5
                       0x9E, 0x06, 0x00, 0x24,  # Antenna pair 3 Channel 5
                       0x15, 0x04, 0x00, 0x24,  # Antenna pair 4 Channel 5
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 5 Channel 5
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 6 Channel 5
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 7 Channel 5
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 8 Channel 5
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 1 Channel 6
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 2 Channel 6
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 3 Channel 6
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 4 Channel 6
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 5 Channel 6
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 6 Channel 6
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 7 Channel 6
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 8 Channel 6
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 1 Channel 8
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 2 Channel 8
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 3 Channel 8
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 4 Channel 8
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 5 Channel 8
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 6 Channel 8
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 7 Channel 8
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 8 Channel 8
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 1 Channel 9
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 2 Channel 9
                       0x63, 0xFE, 0x00, 0x24,  # Antenna pair 3 Channel 9
                       0xB6, 0x07, 0x00, 0x24,  # Antenna pair 4 Channel 9
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 5 Channel 9
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 6 Channel 9
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 7 Channel 9
                       0x00, 0x00, 0x00, 0x24,  # Antenna pair 8 Channel 9
                       0xE4, 0x02, 0x01, 0x00,  # DPD_WAKEUP_SRC
                       0xE4, 0x03, 0x01, 0x14,  # WTX_COUNT_CONFIG
                       0xE4, 0x04, 0x02, 0xF4, 0x01,  # DPD_ENTRY_TIMEOUT
                       ####0xE4, 0x05, 0x01, 0x00,                           # WIFI_COEX_FEATURE
                       ####0xE4, 0x26, 0x01, 0x00,                           # TX_BASE_BAND_CONFIG
                       ####0xE4, 0x28, 0x04, 0x00, 0x00, 0x00, 0x00,         # TX_PULSE_SHAPE_CONFIG
                       ####0xE4, 0x30, 0x02, 0x00, 0x00,                     # CLK_CONFIG_CTRL
                       ####0xE4, 0x31, 0x02, 0xFF, 0x00,                     # HOST_MAX_UCI_PAYLOAD_LENGTH
                       0xE4, 0x33, 0x01, 0x01,  # NXP_EXTENDED_NTF_CONFIG
                       0xE4, 0x28, 0x04, 0x2F, 0x2F, 0x2F, 0x00  # TX_PULSE_CONFIGURATION  # added by Maya
                       ]

# Configure AoA calibration of the UWB device
UWB_CORE_SET_CONFIG_AOA_CALIB_CTRL_RX_ANT_PAIR_1_CH5 = [0x20, 0x04, 0x00, 0xF6,
                                                        0x01,  # Number of parameters
                                                        0xE4, 0x40, 0xF2,  # AOA_CALIB_CTRL_RX_ANT_PAIR_1_CH5
                                                        # Pan  -60,        -48,        -36,        -24,        -12,          0,        +12,        +24,        +36,        +48,        +60,
                                                        0xBB, 0x32, 0x94, 0x26, 0x26, 0x19, 0x23, 0x12, 0x6A, 0x04,
                                                        0x0E, 0xFB, 0x17, 0xF5, 0x90, 0xEA, 0x6B, 0xE7, 0xF6, 0xDB,
                                                        0x82, 0xCF,
                                                        0xC3, 0x31, 0x2E, 0x27, 0x8A, 0x1C, 0x31, 0x11, 0x18, 0x03,
                                                        0x90, 0xF9, 0x01, 0xF3, 0xCF, 0xE7, 0x1A, 0xE3, 0x9E, 0xD9,
                                                        0x17, 0xCE,
                                                        0xB6, 0x2F, 0x0B, 0x26, 0x2D, 0x1C, 0x1A, 0x10, 0x88, 0x01,
                                                        0x09, 0xF8, 0xD3, 0xF1, 0x03, 0xE6, 0xC4, 0xDE, 0xA9, 0xD7,
                                                        0x00, 0xCE,
                                                        0x28, 0x2F, 0xC0, 0x24, 0xAC, 0x19, 0xEF, 0x11, 0x8F, 0x01,
                                                        0x7F, 0xF7, 0x4F, 0xEF, 0x90, 0xE4, 0x93, 0xDC, 0x42, 0xD6,
                                                        0x45, 0xCD,
                                                        0x3E, 0x2E, 0x5E, 0x24, 0xCB, 0x18, 0x6C, 0x11, 0x44, 0x02,
                                                        0x45, 0xF8, 0x94, 0xEE, 0x8E, 0xE3, 0x69, 0xDB, 0x98, 0xD6,
                                                        0x47, 0xCD,
                                                        0x4D, 0x2C, 0x39, 0x23, 0x37, 0x1A, 0x63, 0x0F, 0x5D, 0x02,
                                                        0x0D, 0xF8, 0x6A, 0xEF, 0x98, 0xE4, 0x04, 0xDC, 0x01, 0xD7,
                                                        0xD5, 0xCD,
                                                        0x9F, 0x2A, 0x49, 0x20, 0x63, 0x19, 0xD2, 0x10, 0x3C, 0x04,
                                                        0xBE, 0xF9, 0xD3, 0xEF, 0x1A, 0xE5, 0x86, 0xDD, 0x0A, 0xD7,
                                                        0x2E, 0xD0,
                                                        0x45, 0x29, 0x51, 0x20, 0xCC, 0x15, 0x6A, 0x0C, 0xAF, 0x01,
                                                        0x18, 0xFA, 0xBA, 0xF0, 0xFB, 0xE6, 0x87, 0xDD, 0xEA, 0xD7,
                                                        0x50, 0xD2,
                                                        0x3C, 0x25, 0xDF, 0x1E, 0x3E, 0x14, 0x87, 0x03, 0x5E, 0xFA,
                                                        0xD1, 0xF6, 0x3F, 0xF0, 0x0D, 0xEB, 0xBB, 0xDD, 0x4A, 0xD8,
                                                        0x30, 0xD3,
                                                        0x6D, 0x21, 0xF5, 0x17, 0xF6, 0x11, 0x4C, 0x05, 0x59, 0xF9,
                                                        0x85, 0xF3, 0x50, 0xEC, 0x7E, 0xE7, 0x01, 0xDD, 0x8C, 0xD6,
                                                        0xBD, 0xD3,
                                                        0x42, 0x1D, 0xA1, 0x10, 0x49, 0x0E, 0xCA, 0x08, 0xDA, 0xFC,
                                                        0xE0, 0xEF, 0xF6, 0xE5, 0xE3, 0xE0, 0x3B, 0xDC, 0xB2, 0xD6,
                                                        0xCD, 0xD4
                                                        ]

UWB_CORE_SET_CONFIG_AOA_CALIB_CTRL_RX_ANT_PAIR_2_CH5 = [0x20, 0x04, 0x00, 0xF6,
                                                        0x01,  # Number of parameters
                                                        0xE4, 0x42, 0xF2,  # AOA_CALIB_CTRL_RX_ANT_PAIR_2_CH5
                                                        # Pan  -60,        -48,        -36,        -24,        -12,          0,        +12,        +24,        +36,        +48,        +60,
                                                        0x71, 0xFA, 0x56, 0xFB, 0xA0, 0xFF, 0x28, 0x05, 0x0E, 0x09,
                                                        0x68, 0x0B, 0x54, 0x0F, 0x02, 0x14, 0x7E, 0x15, 0xE1, 0x13,
                                                        0xF1, 0x11,
                                                        0xA1, 0xE9, 0xB4, 0xEF, 0x85, 0xF6, 0xFE, 0xFB, 0x9B, 0x01,
                                                        0xBA, 0x08, 0x78, 0x0F, 0x94, 0x17, 0x06, 0x1E, 0x7C, 0x1C,
                                                        0x4B, 0x16,
                                                        0xB5, 0xE6, 0x73, 0xE9, 0xCC, 0xED, 0xC9, 0xF4, 0x1A, 0xFF,
                                                        0xAC, 0x0A, 0x3A, 0x13, 0xD5, 0x19, 0xC4, 0x23, 0x89, 0x2B,
                                                        0xC4, 0x28,
                                                        0x3F, 0xDA, 0x7E, 0xDD, 0xED, 0xE4, 0xC0, 0xF1, 0x73, 0xFE,
                                                        0xAD, 0x07, 0x6A, 0x14, 0xCF, 0x21, 0xDC, 0x29, 0xB8, 0x31,
                                                        0xAA, 0x38,
                                                        0xC8, 0xD1, 0x16, 0xD8, 0x7A, 0xDE, 0x05, 0xEA, 0x6F, 0xFA,
                                                        0x5B, 0x07, 0x3B, 0x15, 0xBE, 0x25, 0xE4, 0x2F, 0xAA, 0x34,
                                                        0x26, 0x3B,
                                                        0x4D, 0xCA, 0x91, 0xD3, 0xFC, 0xDB, 0xFC, 0xE7, 0x93, 0xF8,
                                                        0x70, 0x05, 0xAB, 0x12, 0xC6, 0x25, 0xD4, 0x31, 0xA3, 0x36,
                                                        0x53, 0x38,
                                                        0xA0, 0xC9, 0xEE, 0xD2, 0x6F, 0xDB, 0x30, 0xE6, 0x9D, 0xF5,
                                                        0x51, 0x03, 0x72, 0x10, 0x81, 0x21, 0x14, 0x2E, 0x65, 0x33,
                                                        0xD9, 0x33,
                                                        0xDA, 0xC4, 0xB8, 0xCF, 0x4F, 0xDA, 0xAD, 0xE5, 0x33, 0xF3,
                                                        0x75, 0x00, 0x2B, 0x0D, 0x2C, 0x1A, 0x4D, 0x27, 0xCC, 0x2F,
                                                        0x24, 0x31,
                                                        0x64, 0xCB, 0xF3, 0xCF, 0xDC, 0xDA, 0x15, 0xE4, 0xD4, 0xEF,
                                                        0xB9, 0xFE, 0x60, 0x0A, 0x75, 0x11, 0x4B, 0x1A, 0xF7, 0x23,
                                                        0xCB, 0x29,
                                                        0x0B, 0xD0, 0xCB, 0xD3, 0x77, 0xDC, 0x48, 0xE8, 0x7B, 0xF2,
                                                        0xD0, 0xFA, 0x2A, 0x04, 0xB8, 0x0D, 0xC1, 0x13, 0xF6, 0x16,
                                                        0x75, 0x1B,
                                                        0x14, 0xDF, 0x5B, 0xE2, 0x12, 0xE8, 0x0D, 0xEF, 0x86, 0xF7,
                                                        0x62, 0xFE, 0x05, 0x05, 0x69, 0x09, 0x63, 0x0C, 0x24, 0x0E,
                                                        0x72, 0x10
                                                        ]

UWB_CORE_SET_CONFIG_AOA_CALIB_CTRL_RX_ANT_PAIR_1_CH9 = [0x20, 0x04, 0x00, 0xF6,
                                                        0x01,  # Number of parameters
                                                        0xE4, 0x41, 0xF2,  # AOA_CALIB_CTRL_RX_ANT_PAIR_1_CH5
                                                        # Tilt -60,        -48,        -36,        -24,        -12,          0,        +12,        +24,        +36,        +48,        +60,
                                                        0x10, 0x43, 0x60, 0x34, 0x31, 0x24, 0x9C, 0x1A, 0x8F, 0x09,
                                                        0x79, 0xF9, 0xD3, 0xE9, 0xF9, 0xD9, 0x23, 0xD3, 0x55, 0xC8,
                                                        0xE6, 0xB8,
                                                        0x2B, 0x3E, 0x4A, 0x36, 0x8B, 0x23, 0x69, 0x1A, 0x8C, 0x08,
                                                        0x0B, 0xFB, 0xCF, 0xEC, 0x95, 0xDC, 0x0B, 0xD1, 0x5F, 0xC7,
                                                        0xC1, 0xB9,
                                                        0x2D, 0x3C, 0xA1, 0x32, 0x5C, 0x27, 0xF9, 0x19, 0xB6, 0x09,
                                                        0xB5, 0xF8, 0xFC, 0xEB, 0x85, 0xDD, 0x32, 0xCE, 0x49, 0xC7,
                                                        0x2B, 0xBB,
                                                        0xD4, 0x3D, 0xC1, 0x2F, 0x19, 0x25, 0x8E, 0x17, 0x40, 0x0A,
                                                        0x60, 0xF7, 0xCB, 0xE6, 0x2B, 0xDB, 0x56, 0xCD, 0x37, 0xC5,
                                                        0x92, 0xBB,
                                                        0x16, 0x40, 0xA0, 0x30, 0x9A, 0x25, 0x86, 0x17, 0x25, 0x08,
                                                        0x11, 0xF9, 0x91, 0xE9, 0x38, 0xDB, 0xBC, 0xCF, 0x48, 0xC5,
                                                        0xD1, 0xBD,
                                                        0x10, 0x40, 0xB7, 0x33, 0x67, 0x2A, 0xA2, 0x1C, 0xBC, 0x09,
                                                        0x59, 0xF9, 0xAD, 0xEC, 0xEA, 0xDC, 0xC3, 0xD1, 0x7C, 0xC8,
                                                        0xDC, 0xBF,
                                                        0x4F, 0x3D, 0xA5, 0x30, 0xA2, 0x26, 0x44, 0x1B, 0x03, 0x09,
                                                        0x29, 0xF9, 0x50, 0xEB, 0x69, 0xDC, 0xDE, 0xD1, 0xE7, 0xC7,
                                                        0xB1, 0xC0,
                                                        0x83, 0x3C, 0xD8, 0x32, 0xEC, 0x28, 0x24, 0x1C, 0x03, 0x10,
                                                        0xEC, 0x00, 0xFF, 0xF0, 0x51, 0xE1, 0xA9, 0xD2, 0x0D, 0xC5,
                                                        0x29, 0xBE,
                                                        0x8B, 0x41, 0x86, 0x3D, 0x30, 0x2E, 0xC4, 0x1F, 0x6B, 0x0C,
                                                        0x23, 0xF9, 0xB7, 0xEC, 0x6F, 0xE0, 0xEF, 0xD2, 0x2C, 0xC6,
                                                        0x94, 0xBB,
                                                        0x1A, 0x47, 0xE8, 0x3B, 0x26, 0x2D, 0x6E, 0x1F, 0x9F, 0x0C,
                                                        0x18, 0xFB, 0x03, 0xE7, 0x62, 0xD8, 0x04, 0xD3, 0x19, 0xC8,
                                                        0xA0, 0xBA,
                                                        0x15, 0x47, 0xDB, 0x34, 0xC1, 0x2F, 0xB8, 0x20, 0x74, 0x0F,
                                                        0xBA, 0xFA, 0x31, 0xE7, 0x85, 0xD7, 0x54, 0xCF, 0xAA, 0xC8,
                                                        0xD4, 0xBB
                                                        ]

UWB_CORE_SET_CONFIG_AOA_CALIB_CTRL_RX_ANT_PAIR_2_CH9 = [0x20, 0x04, 0x00, 0xF6,
                                                        0x01,  # Number of parameters
                                                        0xE4, 0x43, 0xF2,  # AOA_CALIB_CTRL_RX_ANT_PAIR_2_CH5
                                                        # Tilt -60,        -48,        -36,        -24,        -12,          0,        +12,        +24,        +36,        +48,        +60,
                                                        0xD5, 0xD9, 0x6D, 0xD7, 0xB3, 0xDA, 0xDB, 0xE4, 0xAF, 0xF1,
                                                        0x6C, 0xFE, 0xD9, 0x06, 0xEA, 0x09, 0x82, 0x11, 0xDD, 0x1A,
                                                        0x9D, 0x23,
                                                        0x5D, 0xCC, 0xA2, 0xD7, 0x75, 0xDB, 0x3A, 0xE0, 0xFC, 0xEC,
                                                        0xD0, 0x00, 0x67, 0x0C, 0xCB, 0x0F, 0xCF, 0x1D, 0xBB, 0x27,
                                                        0x2C, 0x2D,
                                                        0xA1, 0xC3, 0x20, 0xCF, 0xA8, 0xDF, 0xBC, 0xE3, 0xB3, 0xE9,
                                                        0xD2, 0xFE, 0x4E, 0x0D, 0x05, 0x13, 0x2F, 0x21, 0x05, 0x2D,
                                                        0x65, 0x34,
                                                        0x6E, 0xC2, 0x0F, 0xC7, 0x4B, 0xD6, 0x9C, 0xE5, 0x0C, 0xEA,
                                                        0xAA, 0xFA, 0x00, 0x0E, 0x8F, 0x15, 0x2B, 0x26, 0x91, 0x33,
                                                        0xD7, 0x3C,
                                                        0xF0, 0xC3, 0x84, 0xC5, 0xB9, 0xD0, 0x90, 0xE2, 0x53, 0xEA,
                                                        0x73, 0xF6, 0xB0, 0x0A, 0x1C, 0x17, 0x2E, 0x26, 0x53, 0x35,
                                                        0x70, 0x3F,
                                                        0x1D, 0xC3, 0x71, 0xC7, 0x0A, 0xCE, 0x06, 0xDE, 0xBA, 0xE8,
                                                        0xC2, 0xF4, 0x50, 0x07, 0x86, 0x18, 0x33, 0x25, 0x2F, 0x33,
                                                        0x58, 0x3E,
                                                        0xEE, 0xC0, 0xDD, 0xC6, 0x03, 0xCE, 0x2B, 0xDB, 0xF2, 0xE5,
                                                        0xE2, 0xF3, 0x6C, 0x04, 0x39, 0x17, 0xBF, 0x24, 0x59, 0x2E,
                                                        0xC8, 0x39,
                                                        0x90, 0xC0, 0x1A, 0xC6, 0x32, 0xCF, 0xE9, 0xD9, 0x76, 0xE3,
                                                        0xB8, 0xF3, 0x13, 0x02, 0x52, 0x12, 0x69, 0x22, 0x55, 0x28,
                                                        0xAB, 0x32,
                                                        0xD9, 0xC1, 0xAB, 0xC7, 0x76, 0xD2, 0xD9, 0xD7, 0xD5, 0xE1,
                                                        0xB9, 0xF2, 0x95, 0xFE, 0x04, 0x09, 0x2E, 0x18, 0x82, 0x22,
                                                        0x1C, 0x29,
                                                        0xE9, 0xC7, 0xBA, 0xCA, 0xDA, 0xCF, 0x84, 0xD4, 0x3E, 0xE0,
                                                        0x00, 0xF1, 0x56, 0xFB, 0x6C, 0x00, 0xFD, 0x0B, 0xBF, 0x17,
                                                        0x16, 0x1D,
                                                        0x86, 0xCB, 0x3A, 0xD0, 0x1A, 0xD5, 0xD9, 0xDC, 0x26, 0xE7,
                                                        0x3D, 0xF1, 0x47, 0xF9, 0x3A, 0xFB, 0xE0, 0xFF, 0x96, 0x06,
                                                        0x06, 0x0D
                                                        ]

UWB_CORE_SET_CONFIG_AOA_CALIB_CTRL_AVG_PDOA = [0x20, 0x04, 0x00, 0x5C,
                                               0x01,  # Number of parameters
                                               0xE4, 0x44, 0x58,  # AOA_CALIB_CTRL_AVG_PDOA
                                               0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                               0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                               # Antenna pair 1 Channel 5
                                               0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                               0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                               # Antenna pair 1 Channel 9
                                               0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                               0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                               # Antenna pair 2 Channel 5
                                               0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                               0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
                                               # Antenna pair 2 Channel 9
                                               ]

UWB_CORE_SET_CONFIG_AOA_CALIB_CTRL_TH_PDOA = [0x20, 0x04, 0x00, 0x0C,
                                              0x01,  # Number of parameters
                                              0xE4, 0x45, 0x08,  # AOA_CALIB_CTRL_THRESHOLD_PDOA
                                              0x9F, 0xAC,  # Antenna pair 1 Channel 5
                                              0x63, 0x58,  # Antenna pair 1 Channel 9
                                              0x16, 0xAA,  # Antenna pair 2 Channel 5
                                              0xB7, 0xAD  # Antenna pair 2 Channel 9
                                              ]

# Set Calibration
#   0x00: VCO PLL
#   0x01: TX POWER (Byte1 TX_POWER_ID_RMS, Byte2 TX_POWER_DELTA_PEAK)
#   0x02: 38.4 MHz XTAL CAP
#   0x03: RSSI CALIB CONSTANT1
#   0x04: RSSI CALIB CONSTANT2
#   0x05: SNR CALIB CONSTANT
#   0x06: MANUAL_TX_POW_CTRL
#   0x07: PDOA1_OFFSET
#   0x08: PA_PPA_CALIB_CTRL
#   0x09: TX_TEMPERATURE_COMP
#   0x0A: PDOA2_OFFSET
#   0x0B-0x0F: RFU
UWB_SET_CALIBRATION = [0x2E, 0x11, 0x00, 0x06] + channel_ID + [  # Channel ID
    0x01, 0x1E, 0x01, 0x00, 0x00  # TX_POWER
]

UWB_SET_PDOA1_CALIBRATION = [0x2E, 0x11, 0x00, 0x0A] + channel_ID + [  # Channel ID
    0x07, 0xB5, 0xfD, 0xB5, 0xfD, 0xB5, 0xfD, 0xB5, 0xfD]  # PDOA1_OFFSET, -47,5° = 0xE83F in Q9.7 hex

# only from A25 FW
UWB_SET_PDOA2_CALIBRATION = [0x2E, 0x11, 0x00, 0x0A] + channel_ID + [  # Channel ID
    0x0A, 0x29, 0x01, 0x29, 0x01, 0x29, 0x01, 0x29, 0x01]  # PDOA2_OFFSET, -46,77° = 0xE89D in Q9.7 hex

# Session ID
# SESSION_ID = [0x78, 0x56, 0x34, 0x12]
# SESSION_ID = [0x11, 0x11, 0x11, 0x11]
SESSION_ID = [0x57, 0x04, 0x00, 0x00]

# Create new UWB ranging session
UWB_SESSION_INIT_RANGING = [0x21, 0x00, 0x00, 0x05] + SESSION_ID + [0x00]

# Set Application configurations parameters
# Generic settings
UWB_SESSION_SET_APP_CONFIG = [0x21, 0x03, 0x00, 0xA8] + SESSION_ID + [
    0x2F,  # Number of parameters
    #   0x00, 0x01, 0x00,                                 # DEVICE_TYPE
    0x01, 0x01, 0x02,  # RANGING_ROUND_USAGE
    0x02, 0x01, 0x00,  # STS_CONFIG
    0x03, 0x01, 0x00,  # MULTI_NODE_MODE
    0x04, 0x01] + channel_ID + [  # CHANNEL_NUMBER
                                 0x05, 0x01, 0x01,  # NUMBER_OF_CONTROLEES
                                 #   0x06, 0x02, 0x00, 0x00,                           # DEVICE_MAC_ADDRESS
                                 #   0x07, 0x02, 0x00, 0x00,                           # DST_MAC_ADDRESS
                                 0x08, 0x02, 0x60, 0x09,  # SLOT_DURATION
                                 0x09, 0x04, 0xD8, 0x00, 0x00, 0x00,  # RANGING_INTERVAL
                                 ####0x0A, 0x04, 0x00, 0x00, 0x00, 0x00,               # STS_INDEX
                                 0x0B, 0x01, 0x00,  # MAC_FCS_TYPE
                                 0x0C, 0x01, 0x03,  # RANGING_ROUND_CONTROL
                                 0x0D, 0x01, 0x01,  # AOA_RESULT_REQ
                                 0x0E, 0x01, 0x01,  # RANGE_DATA_NTF_CONFIG
                                 0x0F, 0x02, 0x00, 0x00,  # RANGE_DATA_NTF_PROXIMITY_NEAR
                                 0x10, 0x02, 0x20, 0x4E,  # RANGE_DATA_NTF_PROXIMITY_FAR
                                 #   0x11, 0x01, 0x00                                  # DEVICE_ROLE
                                 0x12, 0x01, 0x03,  # RFRAME_CONFIG
                                 0x14, 0x01, 0x0A,  # PREAMBLE_CODE_INDEX
                                 0x15, 0x01, 0x00,  # SFD_ID
                                 0x16, 0x01, 0x00,  # PSDU_DATA_RATE
                                 0x17, 0x01, 0x01,  # PREAMBLE_DURATION
                                 0x1A, 0x01, 0x01,  # RANGING_TIME_STRUCT
                                 0x1B, 0x01, 0x12,  # SLOTS_PER_RR
                                 0x1C, 0x01, 0x00,  # TX_ADAPTIVE_PAYLOAD_POWER
                                 0x1E, 0x01, 0x01,  # RESPONDER_SLOT_INDEX
                                 0x1F, 0x01, 0x00,  # PRF_MODE
                                 0x22, 0x01, 0x01,  # SCHEDULED_MODE
                                 0x23, 0x01, 0x00,  # KEY_ROTATION
                                 0x24, 0x01, 0x00,  # KEY_ROTATION_RATE
                                 0x25, 0x01, 0x32,  # SESSION_PRIORITY
                                 0x26, 0x01, 0x00,  # MAC_ADDRESS_MODE
                                 ####0x27, 0x02, 0x00, 0x00,                           # VENDOR_ID
                                 ####0x28, 0x06, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   # STATIC_STS_IV
                                 0x29, 0x01, 0x01,  # NUMBER_OF_STS_SEGMENTS
                                 0x2A, 0x02, 0x00, 0x00,  # MAX_RR_RETRY
                                 ####0x2B, 0x04, 0x00, 0x00, 0x00, 0x00,               # UWB_INITIATION_TIME
                                 0x2C, 0x01, 0x00,  # HOPPING_MODE
                                 ####0x2D, 0x01, 0x00,                                 # BLOCK_STRIDE_LENGTH
                                 ####0x2E, 0x01, 0x00,                                 # RESULT_REPORT_CONFIG
                                 0x2F, 0x01, 0x00,  # IN_BAND_TERMINATION_ATTEMPT_COUNT
                                 ####0x30, 0x04, 0x00, 0x00, 0x00, 0x00,               # SUB_SESSION_ID
                                 ####0x31, 0x02, 0x01, 0x00,                           # BPRF_PHR_DATA_RATE
                                 ####0x32, 0x02, 0x00, 0x00,                           # MAX_NUMBER_OF_MEASUREMENT
                                 ####0x33, 0x01, 0x00,                                 # BLINK_RANDOM_INTERVAL
                                 ####0x34, 0x02, 0x00, 0x01,                           # TDOA_REPORT_FREQUENCY
                                 ####0x35, 0x01, 0x01,                                 # STS_LENGTH
                                 # Proprietary
                                 0xE3, 0x00, 0x01, 0x02,  # TOA_MODE
                                 0xE3, 0x01, 0x01, 0x76,  # CIR_CAPTURE_MODE
                                 ####0xE3, 0x02, 0x01, 0x01,                           # MAC_PAYLOAD_ENCRYPTION
                                 ####0xE3, 0x03, 0x01, 0x00,                           # RX_ANTENNA_POLARIZATION_OPTION
                                 0xE3, 0x05, 0x01, 0x03,  # SESSION_SYNC_ATTEMPTS
                                 0xE3, 0x06, 0x01, 0x03,  # SESSION_SHED_ATTEMPTS
                                 0xE3, 0x07, 0x01, 0x00,  # SCHED_STATUS_NTF
                                 0xE3, 0x08, 0x01, 0x00,  # TX_POWER_DELTA_FCC
                                 0xE3, 0x09, 0x01, 0x00,  # TEST_KDF_FEATURE
                                 0xE3, 0x0A, 0x01, 0x01,  # DUAL_AOA_PREAMBLE_STS
                                 0xE3, 0x0B, 0x01, 0x00,  # TX_POWER_TEMP_COMPENSATION
                                 ####0xE3, 0x0C, 0x01, 0x03,                           # WIFI_COEX_MAX_TOLERANCE_COUNT
                                 ####0xE3, 0x0D, 0x01, 0x00,                           # ADAPTIVE_HOPPING_THRESHOLD
                                 0xE3, 0x0E, 0x01, 0x00,  # RX_MODE
                                 0xE3, 0x0F, 0x01, 0x04,  # RX_ANTENNA_SELECTION
                                 0xE3, 0x10, 0x01, 0x01,  # TX_ANTENNA_SELECTION
                                 0xE3, 0x11, 0x01, 0x32,  # MAX_CONTENTION_PHASE_LENGTH
                                 0xE3, 0x12, 0x01, 0x05,  # CONTENTION_PHASE_UPDATE_LENGTH
                                 ####0xE3, 0x13, 0x01, 0x00,                           # AUTHENTICITY_TAG
                                 ####0xE3, 0x14, 0x02, 0x1E, 0x14,                     # RX_NBIC_CONFIG
                                 0xE3, 0x15, 0x01, 0x03  # MAC_CFG
                                 ####0xE3, 0x16, 0x01, 0x00                            # SESSION_INBAND_DATA_TX_BLOCKS
                                 ####0xE3, 0x17, 0x01, 0x00                            # SESSION_INBAND_DATA_RX_BLOCKS
                                 ####0xE3, 0x18, 0x01, 0x00                            # SUSPEND_RANGING
                                 ####0xE3, 0x19, 0x01, 0x00                            # RX_ANTENNA_SELECTION_RFM
                                 ####0xE3, 0x1A, 0x01, 0x00                            # DATA_TRANSFER_MODE
                             ]

# Set Application configurations parameters
# Specific settings for Initiator
UWB_SESSION_SET_INITIATOR_CONFIG = [0x21, 0x03, 0x00, 0x13] + SESSION_ID + [
    0x04,  # Number of parameters
    0x00, 0x01, 0x01,  # DEVICE_TYPE: Controller
    0x06, 0x02, 0x00, 0x00,  # DEVICE_MAC_ADDRESS: 0x0000
    0x07, 0x02, 0x01, 0x00,  # DST_MAC_ADDRESS: 0x0001
    0x11, 0x01, 0x01  # DEVICE_ROLE: Initiator
]

# Set Application configurations parameters
# Specific settings for Responder
UWB_SESSION_SET_RESPONDER_CONFIG = [0x21, 0x03, 0x00, 0x13] + SESSION_ID + [
    0x04,  # Number of parameters
    0x00, 0x01, 0x00,  # DEVICE_TYPE: Controlee
    0x06, 0x02, 0x01, 0x00,  # DEVICE_MAC_ADDRESS: 0x0001
    0x07, 0x02, 0x00, 0x00,  # DST_MAC_ADDRESS: 0x0000
    0x11, 0x01, 0x00  # DEVICE_ROLE: Responder
]

# Set Debug configurations parameters
UWB_SESSION_SET_DEBUG_CONFIG = [0x21, 0x03, 0x00, 0x41] + SESSION_ID + [
    0x0D,  # Number of parameters
    0xE4, 0x00, 0x02, 0x00, 0x00,  # THREAD_SECURE
    0xE4, 0x01, 0x02, 0x00, 0x00,  # THREAD_SECURE_ISR
    0xE4, 0x02, 0x02, 0x00, 0x00,  # THREAD_NON_SECURE_ISR
    0xE4, 0x03, 0x02, 0x00, 0x00,  # THREAD_SHELL
    0xE4, 0x04, 0x02, 0x00, 0x00,  # THREAD_PHY
    0xE4, 0x05, 0x02, 0x00, 0x00,  # THREAD_RANGING
    0xE4, 0x06, 0x02, 0x00, 0x00,  # THREAD_SECURE_ELEMENT
    0xE4, 0x07, 0x02, 0x00, 0x00,  # THREAD_UWB_WLAN_COEX
    0xE4, 0x10, 0x01, 0x00,  # DATA_LOGGER_NTF
    0xE4, 0x11, 0x01, 0x00,  # CIR_LOG_NTF
    0xE4, 0x12, 0x01, 0x00,  # PSDU_LOG_NTF
    0xE4, 0x13, 0x01, 0x00,  # RFRAME_LOG_NTF
    0xE4, 0x14, 0x01, 0x00  # TEST_CONTENTION_RANGING_FEATURE
    ####0xE4, 0x15, 0x04, 0x00, 0x00, 0xFF, 0x03          # CIR_CAPTURE_WINDOW
]

# Start UWB ranging session
UWB_RANGE_START = [0x22, 0x00, 0x00, 0x04] + SESSION_ID

# Stop UWB ranging session
UWB_RANGE_STOP = [0x22, 0x01, 0x00, 0x04] + SESSION_ID

# Deinit UWB session
UWB_SESSION_DEINIT = [0x21, 0x01, 0x00, 0x04] + SESSION_ID


###########################################################
class SIGINThandler():
    def __init__(self):
        self.sigint = False

    def signal_handler(self, signal, frame):
        print("You pressed Ctrl+C!")
        self.sigint = True


class SessionStates():
    def __init__(self):
        self.allow_config = Event()
        self.allow_start = Event()
        self.allow_stop = Event()
        self.allow_end = Event()

    def set(self, status):
        if (status == 0x00):
            # SESSION_STATE_INIT
            self.allow_config.set()
            self.allow_start.clear()
            self.allow_stop.clear()
            self.allow_end.clear()

        if (status == 0x01):
            # SESSION_STATE_DEINIT
            self.allow_config.clear()
            self.allow_start.clear()
            self.allow_stop.clear()
            self.allow_end.set()

        if (status == 0x02):
            # SESSION_STATE_ACTIVE
            self.allow_config.set()
            self.allow_start.set()
            self.allow_stop.set()
            self.allow_end.clear()

        if (status == 0x03):
            # SESSION_STATE_IDLE
            self.allow_config.set()
            self.allow_start.set()
            self.allow_stop.clear()
            self.allow_end.clear()

        if (status == 0xFF):
            # SESSION_ERROR
            self.allow_config.clear()
            self.allow_start.clear()
            self.allow_stop.clear()
            self.allow_end.clear()

    def set_all(self):
        self.allow_config.set()
        self.allow_start.set()
        self.allow_stop.set()
        self.allow_end.set()
    
    def clear_all(self):
        self.allow_config.clear()
        self.allow_start.clear()
        self.allow_stop.clear()
        self.allow_end.clear()
    


###########################################################
serial_port = serial.Serial()
command_queue = queue.Queue(maxsize=100)
session_status = SessionStates()
write_wait = Condition()
go_stop = Event()
stop_write_thread = False
stop_read_thread = False
stop_ipc_thread = False
retry_cmd = False
meas_idx = 1
bin_store = False
cir0_file = ""
cir1_file = ""
rframe_session = ""
rframe_nb = 0
rframe_meas = []
file_ipc = None
socket = None

# Not draw when index is negative
range_plot = {"index": -1, "valid": False, "nlos": 0, "distance": 0,
              "azimuth": 0, "elevation": 0, "avg_azimuth": 0, "avg_elevation": 0}

# Not draw when number of measurement is zero
cir_plot = {"nb_meas": 0, "mappings": [], "cir_samples": []}


# Output string on STDOUT or store into file depending of IPC mode
# Return True is success to write string into file
def output(string):
    global is_ipc
    global file_ipc

    if (is_ipc):
        if ((file_ipc is not None) and (not file_ipc.closed) and (file_ipc.writable())):
            # File available for write
            file_ipc.write(string + "\n")

            return True
    else:
        # Output string on STDOUT
        print(string)

    return False


def deg_to_rad(angle_deg):
    return (angle_deg * np.pi / 180)


def extract_seq_cnt(byte_array):
    return int((byte_array[3] << 24) + (byte_array[2] << 16) + (byte_array[1] << 8) + byte_array[0])


def extract_nlos(byte_array):
    return int(byte_array[28])


def extract_distance(byte_array):
    return int((byte_array[30] << 8) + byte_array[29])


def extract_azimuth(byte_array):
    return int((byte_array[32] << 8) + byte_array[31])


def extract_azimuth_fom(byte_array):
    return int(byte_array[33])


def extract_elevation(byte_array):
    return int((byte_array[35] << 8) + byte_array[34])


def extract_elevation_fom(byte_array):
    return int(byte_array[36])


def extract_cir(byte_array):
    cir_raw = []

    for idx in range(0, len(byte_array), 4):
        cir_sample = byte_array[idx:idx + 4]

        real = twos_comp(int((cir_sample[1] << 8) + cir_sample[0]), 16)
        imaginary = twos_comp(int((cir_sample[3] << 8) + cir_sample[2]), 16)

        cir_raw.append(real + 1j * imaginary)

    return np.abs(cir_raw)


def extract_pdoa1(byte_array):
    return int((byte_array[67] << 8) + byte_array[66])


def extract_pdoa2(byte_array):
    return int((byte_array[71] << 8) + byte_array[70])


def twos_comp(val, bits):
    # Compute the 2's complement of integer val with the width of bits
    if (val & (1 << (bits - 1))) != 0:  # If sign bit is set
        val = val - (1 << bits)  # Compute negative value
    return val


def convert_qformat_to_float(q_in, n_ints, n_fracs, round_of=2):
    bits = n_ints + n_fracs

    # Compute the 2's complement of integer q_in with the width of n_ints + n_fracs
    if (q_in & (1 << (bits - 1))) != 0:  # If sign bit is set
        q_in = q_in - (1 << bits)  # Compute negative value

    # Divide by 2^n_fracs
    frac = q_in / (1 << n_fracs)

    # Return rounded value
    return round(frac, round_of)


def write_to_serial_port():
    global stop_write_thread
    global command_queue
    global session_status
    global go_stop
    global write_wait
    global serial_port
    global retry_cmd
    global is_timestamp

    output("Write to serial port started")
    while (not stop_write_thread):
        if (retry_cmd):
            retry_cmd = False
        else:
            uci_command = command_queue.get()

        if (uci_command[0] == 0xFF and uci_command[1] == 0xFF):
            break

        usb_out_packet = bytearray()
        usb_out_packet.append(0x01)
        usb_out_packet.append(0x00)
        usb_out_packet.append(len(uci_command))
        usb_out_packet.extend(uci_command)

        if (uci_command[0] == 0x21 and uci_command[1] == 0x03):
            # Wait Session State Initialized to send APP Configs
            session_status.allow_config.wait()
        if (uci_command[0] == 0x22 and uci_command[1] == 0x00):
            # Wait Session State Idle to start ranging
            session_status.allow_start.wait()
        if (uci_command[0] == 0x22 and uci_command[1] == 0x01):
            # Wait Session State Activated
            session_status.allow_stop.wait()
            # Wait reach limit of measurements to stop ranging
            go_stop.wait()

        write_wait.acquire()  # Acquire Lock to avoid mixing in output
        if serial_port.isOpen():
            # if (is_timestamp):
            #     output(datetime.now().isoformat(sep=" ", timespec="milliseconds") + "NXPUCIX => " + \
            #            "".join("{:02x} ".format(x) for x in uci_command))
            # else:
            #     output("NXPUCIX => " + "".join("{:02x} ".format(x) for x in uci_command))

            serial_port.write(serial.to_bytes(usb_out_packet))

            # stop_write_thread = True
            
            # Wait the reception of RSP or timeout of 0.25s before allowing send of new CMD
            notified = write_wait.wait(0.25)
            if (not (notified)): retry_cmd = True  # Repeat command if timeout
        write_wait.release()

    output("Write to serial port exited")

current_state = 1
state_time = time.time()
UWB_SESSION_SET_RESPONDER_CONFIG_1 = [0x21, 0x03, 0x00, 0x13] + SESSION_ID + [
                                    0x04,  # Number of parameters
                                    0x00, 0x01, 0x00,  # DEVICE_TYPE: Controlee
                                    0x06, 0x02, 0x01, 0x00,  # DEVICE_MAC_ADDRESS: 0x0001
                                    0x07, 0x02, 0x00, 0x00,  # DST_MAC_ADDRESS: 0x0000
                                    0x11, 0x01, 0x00  # DEVICE_ROLE: Responder
                                    ]
UWB_SESSION_SET_RESPONDER_CONFIG_2 = [0x21, 0x03, 0x00, 0x13] + SESSION_ID + [
                                    0x04,  # Number of parameters
                                    0x00, 0x01, 0x00,  # DEVICE_TYPE: Controlee
                                    0x06, 0x02, 0x01, 0x00,  # DEVICE_MAC_ADDRESS: 0x0001
                                    0x07, 0x02, 0x00, 0x05,  # DST_MAC_ADDRESS: 0x0000
                                    0x11, 0x01, 0x00  # DEVICE_ROLE: Responder
                                    ]
UWB_SESSION_SET_INITIATOR_CONFIG_1 = [0x21, 0x03, 0x00, 0x13] + SESSION_ID + [
                                    0x04,  # Number of parameters
                                    0x00, 0x01, 0x01,  # DEVICE_TYPE: Controller
                                    0x06, 0x02, 0x00, 0x00,  # DEVICE_MAC_ADDRESS: 0x0000
                                    0x07, 0x02, 0x01, 0x00,  # DST_MAC_ADDRESS: 0x0001
                                    0x11, 0x01, 0x01  # DEVICE_ROLE: Initiator
                                    ]
UWB_SESSION_SET_INITIATOR_CONFIG_2 = [0x21, 0x03, 0x00, 0x13] + SESSION_ID + [
                                    0x04,  # Number of parameters
                                    0x00, 0x01, 0x01,  # DEVICE_TYPE: Controller
                                    0x06, 0x02, 0x00, 0x05,  # DEVICE_MAC_ADDRESS: 0x0000
                                    0x07, 0x02, 0x01, 0x00,  # DST_MAC_ADDRESS: 0x0001
                                    0x11, 0x01, 0x01  # DEVICE_ROLE: Initiator
                                    ]

def change_state():
    global command_queue
    global current_state
    global state_time
    global rhodes_role
    print(time.time()-state_time)
    state_time = time.time()
    # command_queue.put(UWB_SET_BOARD_VARIANT)
    # command_queue.put(UWB_RESET_DEVICE)
    # command_queue.put([0x20, 0x02, 0x00, 0x00])  # Get Device Information
    # command_queue.put([0x20, 0x03, 0x00, 0x00])  # Get Device Capability

    # command_queue.put(UWB_CORE_SET_CONFIG)
    # command_queue.put(UWB_CORE_SET_CONFIG_AOA_CALIB_CTRL_RX_ANT_PAIR_1_CH5)
    # command_queue.put(UWB_CORE_SET_CONFIG_AOA_CALIB_CTRL_RX_ANT_PAIR_2_CH5)
    # command_queue.put(UWB_CORE_SET_CONFIG_AOA_CALIB_CTRL_RX_ANT_PAIR_1_CH9)
    # command_queue.put(UWB_CORE_SET_CONFIG_AOA_CALIB_CTRL_RX_ANT_PAIR_2_CH9)
    # command_queue.put(UWB_CORE_SET_CONFIG_AOA_CALIB_CTRL_AVG_PDOA)
    # command_queue.put(UWB_CORE_SET_CONFIG_AOA_CALIB_CTRL_TH_PDOA)
    # command_queue.put(UWB_SET_CALIBRATION)
    # command_queue.put(UWB_SET_PDOA1_CALIBRATION)
    # command_queue.put(UWB_SET_PDOA2_CALIBRATION)

    command_queue.put(UWB_SESSION_DEINIT)
    command_queue.put(UWB_SESSION_INIT_RANGING)
    command_queue.put(UWB_SESSION_SET_APP_CONFIG)
    if(current_state==1):
        # if (rhodes_role == "Initiator"): command_queue.put(UWB_SESSION_SET_INITIATOR_CONFIG_2)
        # if (rhodes_role == "Responder"): command_queue.put(UWB_SESSION_SET_RESPONDER_CONFIG_2)
        command_queue.put(UWB_SESSION_SET_RESPONDER_CONFIG_2)
        current_state = 2
        print("State 2")
    elif(current_state==2):
        # if (rhodes_role == "Initiator"): command_queue.put(UWB_SESSION_SET_INITIATOR_CONFIG_1)
        # if (rhodes_role == "Responder"): command_queue.put(UWB_SESSION_SET_RESPONDER_CONFIG_1)
        command_queue.put(UWB_SESSION_SET_RESPONDER_CONFIG_1)
        current_state = 1
        print("State 1")
    # elif(current_state==3):
    #     if (rhodes_role == "Initiator"): command_queue.put(UWB_SESSION_SET_INITIATOR_CONFIG_2)
    #     if (rhodes_role == "Responder"): command_queue.put(UWB_SESSION_SET_RESPONDER_CONFIG_2)
    #     # command_queue.put(UWB_SESSION_SET_RESPONDER_CONFIG_1)
    #     current_state = 1
    #     print("State 2")
    command_queue.put(UWB_RANGE_START)


def read_from_serial_port():
    global stop_read_thread
    global serial_port
    global write_wait
    global retry_cmd
    global session_status
    global go_stop
    global nb_meas
    global is_timestamp
    global meas_idx
    global bin_store
    global cir0_file
    global cir1_file
    global rframe_session
    global rframe_nb
    global rframe_meas
    global range_plot
    global is_ipc
    global socket

    meas_nlos = 0
    meas_distance = 0
    meas_azimuth = 0
    meas_azimuth_fom = 0
    meas_elevation = 0
    meas_elevation_fom = 0
    meas_pdoa1 = 0
    meas_pdoa2 = 0
    avg_window_size = 15
    hist_distance = []
    hist_azimuth = []
    hist_elevation = []
    hist_pdoa1 = []
    hist_pdoa2 = []
    is_stored = False

    output("Read from serial port started")
    while (not stop_read_thread):
        if serial_port.isOpen():
            if serial_port.isOpen():
                uci_hdr = serial_port.read(4)  # Read header of UCI frame
                write_wait.acquire()  # Acquire Lock to avoid mixing in output
                if len(uci_hdr) == 4:
                    count = uci_hdr[3]
                    if (uci_hdr[1] & 0x80) == 0x80:
                        # Extended length
                        count = int((uci_hdr[3] << 8) + uci_hdr[2])
                    if count > 0:
                        if serial_port.isOpen():
                            uci_payload = serial_port.read(count)  # Read payload of UCI frame

                            # if (is_timestamp):
                            #     is_stored = output(datetime.now().isoformat(sep=" ", timespec="milliseconds") + \
                            #                        "NXPUCIR <= " + "".join("{:02x} ".format(h) for h in uci_hdr) + \
                            #                        "".join("{:02x} ".format(p) for p in uci_payload))
                            # else:
                            #     is_stored = output("NXPUCIR <= " + "".join("{:02x} ".format(h) for h in uci_hdr) + \
                            #                        "".join("{:02x} ".format(p) for p in uci_payload))

                            if len(uci_payload) == count:
                                if (uci_hdr[0] & 0xF0) == 0x40: write_wait.notify()  # Notify the reception of RSP

                                if (uci_hdr[0] == 0x60 and uci_hdr[1] == 0x07 and uci_hdr[3] == 0x01 and \
                                        uci_payload[0] == 0x0A):
                                    # Command retry without wait response
                                    retry_cmd = True
                                    write_wait.notify()

                                if (uci_hdr[0] == 0x61 and uci_hdr[1] == 0x02 and uci_hdr[3] == 0x06):
                                    # Change Session state
                                    session_status.set(uci_payload[4])
                                    if (uci_payload[5] == 0x01):
                                        # Session termination on max RR Retry
                                        go_stop.set()

                                if (uci_hdr[0] == 0x62 and uci_hdr[1] == 0x00):
                                    # RANGE_DATA_NTF
                                    seq_cnt = extract_seq_cnt(uci_payload)
                                    # Check Status
                                    if (uci_payload[27] != 0x00):
                                        output("***** Ranging Error Detected ****")
                                    else:
                                        meas_nlos = (extract_nlos(uci_payload))
                                        meas_distance = (extract_distance(uci_payload))
                                        meas_azimuth = convert_qformat_to_float(extract_azimuth(uci_payload), 9, 7, 1)
                                        meas_azimuth_fom = (extract_azimuth_fom(uci_payload))
                                        meas_elevation = convert_qformat_to_float(extract_elevation(uci_payload), 9, 7,
                                                                                  1)
                                        meas_elevation_fom = (extract_elevation_fom(uci_payload))

                                        # added by maya, 20210618
                                        if (len(uci_payload) > 71):
                                            meas_pdoa1 = convert_qformat_to_float(extract_pdoa1(uci_payload), 9, 7, 7)
                                            meas_pdoa2 = convert_qformat_to_float(extract_pdoa2(uci_payload), 9, 7, 7)

                                        hist_distance.append(meas_distance)
                                        hist_azimuth.append(meas_azimuth)
                                        hist_elevation.append(meas_elevation)
                                        hist_pdoa1.append(meas_pdoa1)
                                        hist_pdoa2.append(meas_pdoa2)

                                        if (len(hist_distance) > avg_window_size): hist_distance.pop(0)
                                        if (len(hist_azimuth) > avg_window_size): hist_azimuth.pop(0)
                                        if (len(hist_elevation) > avg_window_size): hist_elevation.pop(0)
                                        if (len(hist_pdoa1) > avg_window_size): hist_pdoa1.pop(0)
                                        if (len(hist_pdoa2) > avg_window_size): hist_pdoa2.pop(0)

                                        avg_distance = sum(hist_distance) / len(hist_distance)
                                        avg_azimuth = sum(hist_azimuth) / len(hist_azimuth)
                                        avg_elevation = sum(hist_elevation) / len(hist_elevation)
                                        avg_pdoa1 = sum(hist_pdoa1) / len(hist_pdoa1)
                                        avg_pdoa2 = sum(hist_pdoa2) / len(hist_pdoa2)
                                        output(
                                            "***(%d) NLos:%d   Dist:%d   Azimuth:%f (FOM:%d)   Elevation:%f (FOM:%d)  PDoA1:%f   PDoA2:%f" \
                                            % (seq_cnt, meas_nlos, meas_distance, meas_azimuth, meas_azimuth_fom,
                                               meas_elevation, meas_elevation_fom, meas_pdoa1, meas_pdoa2))
                                        # output(
                                        #     "*** Avg Dist:%d   Avg Azimuth:%f   Avg Elevation:%f   Avg_PDoA1:%f   Avg_PDoA2:%f" \
                                        #     % (avg_distance, avg_azimuth, avg_elevation, avg_pdoa1, avg_pdoa2))


                                        if ((not is_ipc) or (is_stored)):
                                            # Increment the number of valid measurements
                                            meas_idx += 1

                                        if (nb_meas > 0 and meas_idx > nb_meas):
                                            go_stop.set()
                                    change_state()
                            else:
                                output("\nExpected Payload bytes is " + str(count) + \
                                       ", Actual Paylod bytes received is " + str(len(uci_payload)))
                        else:
                            output("Port is not opened")
                    else:
                        output("\nUCI Payload Size is Zero")
                else:
                    output("\nUCI Header is not valid")
                write_wait.release()
            else:
                output("Port is not opened (2)")
        else:
            output("Port is not opened (1)")

    if serial_port.isOpen(): serial_port.close()

    output("Read from serial port exited")


def serial_port_configure():
    global serial_port
    serial_port.baudrate = 115200
    serial_port.timeout = 1  # To avoid endless blocking read
    serial_port.port = com_port


def open_serial_port():
    global serial_port
    if serial_port.isOpen(): serial_port.close()
    try:
        serial_port.open()
    except:
        output("#=> Fail to open " + com_port)
        sys.exit(1)


def start_processing():
    global stop_ipc_thread
    global stop_read_thread
    global stop_write_thread
    global session_status
    global is_range_plot
    global is_cir_plot
    global is_ipc
    global rhodes_role
    global range_plot
    global cir_plot
    global command_queue
    global go_stop

    stop_read_thread = False
    read_thread = Thread(target=read_from_serial_port, args=())
    read_thread.start()

    stop_write_thread = False
    write_thread = Thread(target=write_to_serial_port, args=())
    write_thread.start()

    handler = SIGINThandler()
    signal.signal(signal.SIGINT, handler.signal_handler)

    start_time = time.time()

    # session_status.allow_end.set()

    # while (session_status.allow_end.is_set() == False):
    while(1):
        current_time = time.time()
        if(current_time-start_time>=5):
            print("Time elapsed since reset = " + str(current_time-start_time))
            start_time = time.time()
            # change_state()

        if handler.sigint:
            break
    
    # To restore output on STDOUT
    is_ipc = False

    # End of processing
    stop_write_thread = True
    stop_read_thread = True
    stop_ipc_thread = True

    # Unblock the waiting in the write thread
    command_queue.put([0xFF, 0xFF])  # End of write
    session_status.set_all()
    go_stop.set()


def reset_stuff():
    global serial_port
    global command_queue
    global session_status
    global write_wait
    global go_stop
    global stop_write_thread
    global stop_read_thread
    global stop_ipc_thread
    global retry_cmd
    global meas_idx
    global bin_store
    global cir0_file
    global cir1_file
    global rframe_session
    global rframe_nb
    global rframe_meas
    global file_ipc
    global socket

    # serial_port = serial.Serial()
    open_serial_port()

    command_queue = queue.Queue(maxsize=100)
    session_status.clear_all()
    go_stop.clear()

    stop_write_thread = False
    stop_read_thread = False
    stop_ipc_thread = False
    retry_cmd = False
    meas_idx = 1
    bin_store = False
    cir0_file = ""
    cir1_file = ""
    rframe_session = ""
    rframe_nb = 0
    rframe_meas = []
    # file_ipc = None
    # socket = None

def main():
    global nb_meas
    global rhodes_role
    global com_port
    global is_timestamp
    global is_range_plot
    global is_cir_plot
    global bin_store
    global is_ipc
    global prefix_ipc
    global file_ipc
    global command_queue

    path = ""

    for arg in sys.argv[1:]:
        if (arg.isdecimal()):
            nb_meas = int(arg)
        elif (arg == "i"):
            rhodes_role = "Initiator"
        elif (arg == "r"):
            rhodes_role = "Responder"
        elif (arg.startswith("COM")):
            com_port = arg
        elif (arg == "notime"):
            is_timestamp = False
        elif (arg == "noplot"):
            is_range_plot = False
            is_cir_plot = False
        elif (arg == "nocirplot"):
            is_range_plot = True
            is_cir_plot = False
        elif (arg == "ipc"):
            is_ipc = True
        else:
            path = arg

    is_range_plot = False
    is_cir_plot = False

    output("Role:" + rhodes_role + "   Port:" + com_port + "   Nb Meas:" + str(nb_meas) + "   Timestamp:" + str(
        is_timestamp) + \
           "   Range Plot:" + str(is_range_plot) + "   CIR Plot:" + str(is_cir_plot) + "   IPC:" + str(is_ipc))

    output("Configure serial port...")
    serial_port_configure()
    output("Serial port configured")

    repeat_this = 5

    if(repeat_this):
        # reset_stuff()

        open_serial_port()

        # Add the UCI Commands to sent
        output("Start adding commands to the queue...")
        command_queue.put(UWB_SET_BOARD_VARIANT)
        command_queue.put(UWB_RESET_DEVICE)
        command_queue.put([0x20, 0x02, 0x00, 0x00])  # Get Device Information
        command_queue.put([0x20, 0x03, 0x00, 0x00])  # Get Device Capability

        command_queue.put(UWB_CORE_SET_CONFIG)
        command_queue.put(UWB_CORE_SET_CONFIG_AOA_CALIB_CTRL_RX_ANT_PAIR_1_CH5)
        command_queue.put(UWB_CORE_SET_CONFIG_AOA_CALIB_CTRL_RX_ANT_PAIR_2_CH5)
        command_queue.put(UWB_CORE_SET_CONFIG_AOA_CALIB_CTRL_RX_ANT_PAIR_1_CH9)
        command_queue.put(UWB_CORE_SET_CONFIG_AOA_CALIB_CTRL_RX_ANT_PAIR_2_CH9)
        command_queue.put(UWB_CORE_SET_CONFIG_AOA_CALIB_CTRL_AVG_PDOA)
        command_queue.put(UWB_CORE_SET_CONFIG_AOA_CALIB_CTRL_TH_PDOA)
        command_queue.put(UWB_SET_CALIBRATION)
        command_queue.put(UWB_SET_PDOA1_CALIBRATION)
        command_queue.put(UWB_SET_PDOA2_CALIBRATION)

        command_queue.put(UWB_SESSION_INIT_RANGING)
        command_queue.put(UWB_SESSION_SET_APP_CONFIG)
        if (rhodes_role == "Initiator"): command_queue.put(UWB_SESSION_SET_INITIATOR_CONFIG)
        if (rhodes_role == "Responder"): command_queue.put(UWB_SESSION_SET_RESPONDER_CONFIG)
        command_queue.put(UWB_SESSION_SET_DEBUG_CONFIG)

        command_queue.put(UWB_RANGE_START)
        if (nb_meas > 0):
            command_queue.put(UWB_RANGE_STOP)
            command_queue.put(UWB_SESSION_DEINIT)
        output("adding commands to the queue completed")


        # start_time = time.time()
        output("Start processing...")
        start_processing()
        output("Processing finished")
        # print(time.time()-start_time)

        repeat_this = repeat_this - 1


if __name__ == "__main__":
    main()
