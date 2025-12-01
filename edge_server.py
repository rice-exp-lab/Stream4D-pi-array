#!/usr/bin/env python3

import argparse
import base64
import json
import socket
import threading
import time
from math import cos, sin, radians

import numpy as np
import cv2
import matplotlib.pyplot as plt

# Dict: node_id -> latest data
data_lock = threading.Lock()
latest = {}  # { node_id: {"timestamp": str, "frame_rgb": np.array, "uwb": {...}} }


def handle_client(conn, addr):
    print(f"[NET] Connection from {addr}")
    f = conn.makefile("r")  # text mode for JSON lines
    try:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                print("[NET] JSON decode error, skipping")
                continue

            node_id = msg.get("node_id", "unknown")
            ts = msg.get("timestamp")
            uwb = msg.get("uwb", {})

            img_b64 = msg.get("image_b64")
            if not img_b64:
                continue

            # Decode JPEG
            try:
                img_bytes = base64.b64decode(img_b64)
                np_arr = np.frombuffer(img_bytes, np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            except Exception as e:
                print("[IMG] Decode error:", e)
                continue

            with data_lock:
                latest[node_id] = {
                    "timestamp": ts,
                    "frame_rgb": frame_rgb,
                    "uwb": uwb,
                }

    except Exception as e:
        print("[NET] Client error:", e)
    finally:
        conn.close()
        print(f"[NET] Connection closed for {addr}")


def server_thread(port):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(5)
    print(f"[NET] Listening on 0.0.0.0:{port}")

    while True:
        conn, addr = srv.accept()
        t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        t.start()


def main():
    parser = argparse.ArgumentParser(description="Desktop multi-node visualizer")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--node1-id", default="node1")
    parser.add_argument("--node2-id", default="node2")
    args = parser.parse_args()

    # Start server
    t_srv = threading.Thread(target=server_thread, args=(args.port,), daemon=True)
    t_srv.start()

    # Matplotlib setup
    plt.ion()
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    ax1, ax2, ax3 = axes
    ax1.set_title(f"{args.node1-id} frame")
    ax2.set_title(f"{args.node2-id} frame")
    ax3.set_title("Relative positions (UWB)")
    ax3.set_xlabel("X (cm)")
    ax3.set_ylabel("Y (cm)")
    ax3.set_aspect("equal", adjustable="box")

    im1 = ax1.imshow(np.zeros((240, 320, 3), dtype=np.uint8))
    im2 = ax2.imshow(np.zeros((240, 320, 3), dtype=np.uint8))

    # Keep scatter handles so we can update
    scatter_nodes = None

    try:
        while True:
            with data_lock:
                d1 = latest.get(args.node1_id)
                d2 = latest.get(args.node2_id)

            # Update frames
            if d1 and "frame_rgb" in d1:
                im1.set_data(d1["frame_rgb"])
                ax1.set_title(f"{args.node1_id} @ {d1['timestamp']}")
            if d2 and "frame_rgb" in d2:
                im2.set_data(d2["frame_rgb"])
                ax2.set_title(f"{args.node2_id} @ {d2['timestamp']}")

            # Update UWB positions (simple polar -> cartesian)
            xs, ys, labels = [], [], []
            if d1 and d1.get("uwb"):
                u1 = d1["uwb"]
                dist = u1.get("distance_cm")
                az = u1.get("azimuth_deg")
                if dist is not None and az is not None:
                    x = dist * cos(radians(az))
                    y = dist * sin(radians(az))
                    xs.append(x)
                    ys.append(y)
                    labels.append(args.node1_id)

            if d2 and d2.get("uwb"):
                u2 = d2["uwb"]
                dist = u2.get("distance_cm")
                az = u2.get("azimuth_deg")
                if dist is not None and az is not None:
                    x = dist * cos(radians(az))
                    y = dist * sin(radians(az))
                    xs.append(x)
                    ys.append(y)
                    labels.append(args.node2_id)

            ax3.clear()
            ax3.set_title("Relative positions (UWB)")
            ax3.set_xlabel("X (cm)")
            ax3.set_ylabel("Y (cm)")
            ax3.set_aspect("equal", adjustable="box")
            ax3.axhline(0, color="grey", linewidth=0.5)
            ax3.axvline(0, color="grey", linewidth=0.5)

            if xs and ys:
                ax3.scatter(xs, ys)
                for x, y, label in zip(xs, ys, labels):
                    ax3.text(x, y, label)

            plt.pause(0.05)  # ~20 FPS GUI update

    except KeyboardInterrupt:
        print("\n[MAIN] Ctrl+C, exiting...")
    finally:
        plt.ioff()
        plt.show()


if __name__ == "__main__":
    main()
