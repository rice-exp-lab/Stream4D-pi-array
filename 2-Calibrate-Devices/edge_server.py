#!/usr/bin/env python3

import argparse
import base64
import json
import socket
import threading
from math import cos, sin, radians

import numpy as np
import cv2
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  (needed for 3D)


# Dict: node_id -> latest data
data_lock = threading.Lock()
latest = {}  # { node_id: {"timestamp": str, "frame_rgb": np.array, "uwb": {...}, "imu": {...}} }


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
                print("[NET] JSON decode error, skipping a line")
                continue

            node_id = msg.get("node_id", "unknown")
            ts = msg.get("timestamp")
            uwb = msg.get("uwb", {})
            imu = msg.get("imu", {})

            img_b64 = msg.get("image_b64")
            if not img_b64:
                continue

            # Decode JPEG
            try:
                img_bytes = base64.b64decode(img_b64)
                np_arr = np.frombuffer(img_bytes, np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                if frame is None:
                    continue
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            except Exception as e:
                print("[IMG] Decode error:", e)
                continue

            with data_lock:
                latest[node_id] = {
                    "timestamp": ts,
                    "frame_rgb": frame_rgb,
                    "uwb": uwb,
                    "imu": imu,
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


def spherical_to_cartesian(dist_cm, az_deg, el_deg):
    """
    Convert spherical (distance, azimuth, elevation) to Cartesian (x,y,z).

    dist_cm : radius in cm
    az_deg  : azimuth in degrees (0 = +X axis, CCW towards +Y)
    el_deg  : elevation in degrees (0 = XY plane, + up)
    """
    r = float(dist_cm)
    az = radians(float(az_deg))
    el = radians(float(el_deg))

    x = r * cos(el) * cos(az)
    y = r * cos(el) * sin(az)
    z = r * sin(el)
    return x, y, z


def orientation_vector_from_imu(imu):
    """
    Use heading (yaw) + pitch to generate a 3D orientation vector.

    heading: yaw in degrees
    pitch  : pitch in degrees
    """
    heading = imu.get("heading")
    pitch = imu.get("pitch")

    if heading is None or pitch is None:
        return None

    try:
        yaw_rad = radians(float(heading))
        pitch_rad = radians(float(pitch))
    except (TypeError, ValueError):
        return None

    # Simple forward vector in sensor frame
    vx = cos(pitch_rad) * cos(yaw_rad)
    vy = cos(pitch_rad) * sin(yaw_rad)
    vz = sin(pitch_rad)
    return vx, vy, vz


def main():
    parser = argparse.ArgumentParser(description="Desktop multi-node 3D viewer")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--node1-id", default="node1")
    parser.add_argument("--node2-id", default="node2")
    args = parser.parse_args()

    # Start TCP server
    t_srv = threading.Thread(target=server_thread, args=(args.port,), daemon=True)
    t_srv.start()

    # --- Matplotlib setup ---
    plt.ion()
    fig = plt.figure(figsize=(15, 5))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.2])

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[0, 2], projection="3d")

    ax1.set_title(f"{args.node1_id} frame")
    ax2.set_title(f"{args.node2_id} frame")
    ax1.axis("off")
    ax2.axis("off")

    # Initial blank images
    im1 = ax1.imshow(np.zeros((240, 320, 3), dtype=np.uint8))
    im2 = ax2.imshow(np.zeros((240, 320, 3), dtype=np.uint8))

    try:
        while True:
            with data_lock:
                d1 = latest.get(args.node1_id)
                d2 = latest.get(args.node2_id)

            # Update image panels
            if d1 and "frame_rgb" in d1:
                im1.set_data(d1["frame_rgb"])
                ax1.set_title(f"{args.node1_id} @ {d1['timestamp']}")
            if d2 and "frame_rgb" in d2:
                im2.set_data(d2["frame_rgb"])
                ax2.set_title(f"{args.node2_id} @ {d2['timestamp']}")

            # --- Update 3D plot ---
            ax3.cla()
            ax3.set_title("Relative positions & orientation (UWB + IMU)")
            ax3.set_xlabel("X (cm)")
            ax3.set_ylabel("Y (cm)")
            ax3.set_zlabel("Z (cm)")

            xs, ys, zs, labels, arrows = [], [], [], [], []

            # Node 1
            if d1:
                u1 = d1.get("uwb", {})
                if u1:
                    dist = u1.get("distance_cm")
                    az = u1.get("azimuth_deg")
                    el = u1.get("elevation_deg")
                    if dist is not None and az is not None and el is not None:
                        try:
                            x1, y1, z1 = spherical_to_cartesian(dist, az, el)
                            xs.append(x1)
                            ys.append(y1)
                            zs.append(z1)
                            labels.append(args.node1_id)

                            v1 = orientation_vector_from_imu(d1.get("imu", {}))
                            if v1 is not None:
                                arrows.append((x1, y1, z1, *v1))
                        except Exception:
                            pass

            # Node 2
            if d2:
                u2 = d2.get("uwb", {})
                if u2:
                    dist = u2.get("distance_cm")
                    az = u2.get("azimuth_deg")
                    el = u2.get("elevation_deg")
                    if dist is not None and az is not None and el is not None:
                        try:
                            x2, y2, z2 = spherical_to_cartesian(dist, az, el)
                            xs.append(x2)
                            ys.append(y2)
                            zs.append(z2)
                            labels.append(args.node2_id)

                            v2 = orientation_vector_from_imu(d2.get("imu", {}))
                            if v2 is not None:
                                arrows.append((x2, y2, z2, *v2))
                        except Exception:
                            pass

            # Draw nodes and orientation
            if xs and ys and zs:
                ax3.scatter(xs, ys, zs, s=40)
                for x, y, z, label in zip(xs, ys, zs, labels):
                    ax3.text(x, y, z, label)

                # Draw orientation arrows
                max_abs_coord = max(max(abs(v) for v in xs + ys + zs), 10.0)
                for (x, y, z, vx, vy, vz) in arrows:
                    ax3.quiver(
                        x, y, z,
                        vx, vy, vz,
                        length=0.2 * max_abs_coord,
                        normalize=True,
                    )

                # Set symmetric limits
                ax3.set_xlim(-max_abs_coord, max_abs_coord)
                ax3.set_ylim(-max_abs_coord, max_abs_coord)
                ax3.set_zlim(-max_abs_coord, max_abs_coord)

            plt.pause(0.05)  # GUI update ~20 FPS

    except KeyboardInterrupt:
        print("\n[MAIN] Ctrl+C, exiting...")
    finally:
        plt.ioff()
        plt.show()


if __name__ == "__main__":
    main()
