#!/usr/bin/env python3

import argparse
import base64
import json
import socket
import threading
from math import cos, sin, radians, sqrt

import numpy as np
import cv2
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401


# Shared state
data_lock = threading.Lock()
latest = {}       # node_id -> {"timestamp", "frame_rgb", "uwb", "imu"}
node_order = []   # order nodes appear (for reference node)

# Trajectory history: node_id -> {"x": [], "y": [], "z": []}
positions_hist = {}
MAX_HISTORY = 500  # max points to keep per node

NODE_COLORS = [
    "tab:blue",
    "tab:orange",
    "tab:green",
    "tab:red",
    "tab:purple",
    "tab:brown",
]


def handle_client(conn, addr):
    print(f"[NET] Connection from {addr}")
    f = conn.makefile("r")
    try:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                print("[NET] JSON decode error, skipping line")
                continue

            node_id = msg.get("node_id", "unknown")
            ts = msg.get("timestamp")
            uwb = msg.get("uwb", {})
            imu = msg.get("imu", {})
            img_b64 = msg.get("image_b64")

            if not img_b64:
                continue

            # Decode + rotate 180°
            try:
                img_bytes = base64.b64decode(img_b64)
                np_arr = np.frombuffer(img_bytes, np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                if frame is None:
                    continue
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame_rgb = np.rot90(frame_rgb, 2)
            except Exception as e:
                print("[IMG] decode error:", e)
                continue

            with data_lock:
                if node_id not in node_order:
                    node_order.append(node_id)
                    print(f"[INFO] New node: {node_id} (index {len(node_order)-1})")
                latest[node_id] = {
                    "timestamp": ts,
                    "frame_rgb": frame_rgb,
                    "uwb": uwb,
                    "imu": imu,
                }

    except Exception as e:
        print("[NET] client error:", e)
    finally:
        conn.close()
        print(f"[NET] connection closed {addr}")


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
    r = float(dist_cm)
    az = radians(float(az_deg))
    el = radians(float(el_deg))
    x = r * cos(el) * cos(az)
    y = r * cos(el) * sin(az)
    z = r * sin(el)
    return x, y, z


def orientation_vector_from_imu(imu):
    heading = imu.get("heading")
    pitch = imu.get("pitch")
    if heading is None or pitch is None:
        return None
    try:
        yaw_rad = radians(float(heading))
        pitch_rad = radians(float(pitch))
    except (TypeError, ValueError):
        return None
    vx = cos(pitch_rad) * cos(yaw_rad)
    vy = cos(pitch_rad) * sin(yaw_rad)
    vz = sin(pitch_rad)
    return vx, vy, vz


def main():
    parser = argparse.ArgumentParser(description="Desktop 3D viewer for Pi nodes")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    t_srv = threading.Thread(target=server_thread, args=(args.port,), daemon=True)
    t_srv.start()

    # Layout: images on top, big 3D on bottom
    plt.ion()
    fig = plt.figure(figsize=(12, 8))
    gs = fig.add_gridspec(2, 1, height_ratios=[1, 1.2])
    gs_top = gs[0].subgridspec(1, 2)

    ax1 = fig.add_subplot(gs_top[0, 0])
    ax2 = fig.add_subplot(gs_top[0, 1])
    ax3 = fig.add_subplot(gs[1, 0], projection="3d")

    ax1.set_title("pinode0 frame")
    ax2.set_title("pinode1 frame")
    ax1.axis("off")
    ax2.axis("off")

    im1 = None
    im2 = None

    try:
        while True:
            with data_lock:
                node_ids = list(node_order)
                data_snap = {nid: latest.get(nid) for nid in node_ids}

            if not node_ids:
                plt.pause(0.05)
                continue

            # Reference node is first node
            ref_id = node_ids[0]
            id_to_label = {nid: f"pinode{i}" for i, nid in enumerate(node_ids)}

            # ---------- update image panels ----------
            if len(node_ids) > 0:
                n0 = node_ids[0]
                d0 = data_snap.get(n0)
                if d0 and "frame_rgb" in d0:
                    frame0 = d0["frame_rgb"]
                    if im1 is None:
                        im1 = ax1.imshow(frame0, interpolation="none")
                        ax1.set_aspect("equal", adjustable="box")
                    else:
                        im1.set_data(frame0)
                    ax1.set_title(f"{id_to_label[n0]} @ {d0['timestamp']}")

            if len(node_ids) > 1:
                n1 = node_ids[1]
                d1 = data_snap.get(n1)
                if d1 and "frame_rgb" in d1:
                    frame1 = d1["frame_rgb"]
                    if im2 is None:
                        im2 = ax2.imshow(frame1, interpolation="none")
                        ax2.set_aspect("equal", adjustable="box")
                    else:
                        im2.set_data(frame1)
                    ax2.set_title(f"{id_to_label[n1]} @ {d1['timestamp']}")
            # -----------------------------------------

            # ---------- 3D plot ----------
            ax3.cla()
            ax3.set_title("Relative positions & orientation (UWB + IMU)")
            ax3.set_xlabel("X (cm)")
            ax3.set_ylabel("Y (cm)")
            ax3.set_zlabel("Z (cm)")

            positions = {}   # node_id -> (x,y,z)
            arrows = []

            # reference at origin
            positions[ref_id] = (0.0, 0.0, 0.0)
            d_ref = data_snap.get(ref_id)
            if d_ref:
                v_ref = orientation_vector_from_imu(d_ref.get("imu", {}))
                color_ref = NODE_COLORS[0 % len(NODE_COLORS)]
                if v_ref is not None:
                    arrows.append((*positions[ref_id], *v_ref, color_ref))

            # other nodes from their UWB relative to ref
            for i, nid in enumerate(node_ids):
                if nid == ref_id:
                    continue
                d = data_snap.get(nid)
                if not d:
                    continue
                uwb = d.get("uwb", {})
                dist = uwb.get("distance_cm")
                az = uwb.get("azimuth_deg")
                el = uwb.get("elevation_deg")
                if dist is None or az is None or el is None:
                    continue
                try:
                    x, y, z = spherical_to_cartesian(dist, az, el)
                except Exception:
                    continue
                positions[nid] = (x, y, z)
                v = orientation_vector_from_imu(d.get("imu", {}))
                color = NODE_COLORS[i % len(NODE_COLORS)]
                if v is not None:
                    arrows.append((x, y, z, *v, color))

            # update trajectory history
            for i, nid in enumerate(node_ids):
                if nid not in positions:
                    continue
                x, y, z = positions[nid]
                hist = positions_hist.setdefault(
                    nid, {"x": [], "y": [], "z": []}
                )
                hist["x"].append(x)
                hist["y"].append(y)
                hist["z"].append(z)
                # keep history short
                if len(hist["x"]) > MAX_HISTORY:
                    hist["x"].pop(0)
                    hist["y"].pop(0)
                    hist["z"].pop(0)

            # draw trajectories + current points
            all_coords = []
            for i, nid in enumerate(node_ids):
                if nid not in positions_hist:
                    continue
                hist = positions_hist[nid]
                color = NODE_COLORS[i % len(NODE_COLORS)]
                if len(hist["x"]) > 1:
                    ax3.plot(
                        hist["x"],
                        hist["y"],
                        hist["z"],
                        color=color,
                        alpha=0.8,
                        linewidth=2,
                    )
                if nid in positions:
                    x, y, z = positions[nid]
                    ax3.scatter([x], [y], [z], s=60, color=color)
                    ax3.text(
                        x,
                        y,
                        z,
                        id_to_label.get(nid, nid),
                    )
                    all_coords.extend([x, y, z])

            # line and distance between ref and first other node (if exists)
            distance_text = "N/A"
            if len(node_ids) > 1 and ref_id in positions:
                ref_pos = positions[ref_id]
                other_id = node_ids[1]  # second node in session
                if other_id in positions:
                    x0, y0, z0 = ref_pos
                    x1, y1, z1 = positions[other_id]
                    ax3.plot(
                        [x0, x1],
                        [y0, y1],
                        [z0, z1],
                        color="k",
                        linestyle="--",
                        linewidth=1.5,
                    )
                    dx = x1 - x0
                    dy = y1 - y0
                    dz = z1 - z0
                    dist_cm = sqrt(dx * dx + dy * dy + dz * dz)
                    distance_text = f"{dist_cm:.1f} cm"
                    all_coords.extend([x0, y0, z0, x1, y1, z1])

            # axis limits
            if all_coords:
                max_range = max(max(abs(c) for c in all_coords), 10.0)
                ax3.set_xlim(-max_range, max_range)
                ax3.set_ylim(-max_range, max_range)
                ax3.set_zlim(-max_range, max_range)

            # draw orientation arrows
            for (x, y, z, vx, vy, vz, color) in arrows:
                if not all(np.isfinite([x, y, z, vx, vy, vz])):
                    continue
                length = 0.25 * (ax3.get_xlim()[1] - ax3.get_xlim()[0])
                ax3.quiver(
                    x,
                    y,
                    z,
                    vx,
                    vy,
                    vz,
                    length=length,
                    normalize=True,
                    color=color,
                )

            # show distance in text
            ax3.text2D(
                0.02,
                0.95,
                f"Distance pinode0 ↔ pinode1: {distance_text}",
                transform=ax3.transAxes,
            )

            plt.tight_layout()
            plt.pause(0.05)

    except KeyboardInterrupt:
        print("\n[MAIN] Ctrl+C, exiting...")
    finally:
        plt.ioff()
        plt.show()


if __name__ == "__main__":
    main()
