#!/usr/bin/env python3

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
from matplotlib.animation import FuncAnimation
import math

# -------- USER CONFIG --------
REFERENCE_NODE = 2   # 1 or 2: which node's UWB you want to trust for geometry
NODE1_CSV = "2-Calibrate-Devices/output/session_node1/node1_frames.csv"
NODE2_CSV = "2-Calibrate-Devices/output/session_node2/node2_frames.csv"

# Playback speed: 1.0 ~ real-ish, >1 faster, <1 slower
PLAYBACK_SPEED = 1.0
# -----------------------------


def spherical_to_cartesian(dist_cm, az_deg, el_deg):
    if np.isnan(dist_cm) or np.isnan(az_deg) or np.isnan(el_deg):
        return np.nan, np.nan, np.nan
    r = float(dist_cm)
    az = math.radians(float(az_deg))
    el = math.radians(float(el_deg))
    x = r * math.cos(el) * math.cos(az)
    y = r * math.cos(el) * math.sin(az)
    z = r * math.sin(el)
    return x, y, z


def main():
    df1 = pd.read_csv(NODE1_CSV)
    df2 = pd.read_csv(NODE2_CSV)

    if REFERENCE_NODE == 1:
        df = df1
        label = "node1 (reference)"
        ref_name = "Node 1"
        other_name = "Node 0"
    else:
        df = df2
        label = "node2 (reference)"
        ref_name = "Node 0"
        other_name = "Node 1"

    frame = df["frame_index"].to_numpy()
    dist = df["uwb_distance_cm"].to_numpy()
    az   = df["uwb_azimuth_deg"].to_numpy()
    el   = df["uwb_elevation_deg"].to_numpy()
    nlos = df["uwb_nlos_status"].to_numpy()

    # Optional time column (for nicer labels)
    time_col = None
    for c in ["img_timestamp_iso", "uwb_timestamp", "imu_timestamp", "timestamp"]:
        if c in df.columns:
            time_col = c
            break

    if time_col is not None:
        times = pd.to_datetime(df[time_col])
        t0 = times.iloc[0]
        time_axis = (times - t0).dt.total_seconds().to_numpy()
        x_label = f"time since first sample (s) [{time_col}]"
    else:
        times = None
        time_axis = frame.astype(float)
        x_label = "frame index"

    # Cartesian coordinates from THIS node's point of view
    xs, ys, zs = [], [], []
    for d, a, e in zip(dist, az, el):
        x, y, z = spherical_to_cartesian(d, a, e)
        xs.append(x)
        ys.append(y)
        zs.append(z)
    xs = np.array(xs)
    ys = np.array(ys)
    zs = np.array(zs)

    # ---- Matplotlib figure ----
    fig = plt.figure(figsize=(14, 8))
    gs = plt.GridSpec(2, 2, height_ratios=[2, 1], width_ratios=[2, 1])

    # 3D track (this node's view of the other node)
    ax3d = fig.add_subplot(gs[0, 0], projection="3d")
    ax3d.set_title(f"Relative 3D position from {label}")
    ax3d.set_xlabel("X (cm)")
    ax3d.set_ylabel("Y (cm)")
    ax3d.set_zlabel("Z (cm)")

    # Precompute symmetric axis limits
    valid = np.concatenate([
        xs[~np.isnan(xs)],
        ys[~np.isnan(ys)],
        zs[~np.isnan(zs)],
    ])
    if len(valid) > 0:
        m = max(np.max(np.abs(valid)), 10.0)
    else:
        m = 10.0
    ax3d.set_xlim(-m, m)
    ax3d.set_ylim(-m, m)
    ax3d.set_zlim(-m, m)

    # --- NEW: reference node at origin ---
    # This is the reference node in its own coordinate frame
    ref_point, = ax3d.plot(
        [0], [0], [0],
        marker="^", linestyle="None", label=f"{ref_name} (reference)"
    )

    # Line for trajectory and marker for current point (other node)
    line3d, = ax3d.plot([], [], [], marker="o", linestyle="-", label=f"{other_name} path")
    current_point, = ax3d.plot([], [], [], marker="o", linestyle="None", label=f"{other_name} current")

    # Distance vs frame/time
    axd = fig.add_subplot(gs[1, 0])
    axd.set_title("Distance between nodes (UWB range)")
    axd.set_xlabel(x_label)
    axd.set_ylabel("Distance (cm)")
    axd.plot(time_axis, dist, alpha=0.3)  # faint full curve in background

    # marker on distance curve
    dist_marker, = axd.plot([], [], marker="o", linestyle="None")

    # mark NLoS points as red dots on full curve
    nlos_mask = (nlos == 1)
    if np.any(nlos_mask):
        axd.scatter(time_axis[nlos_mask], dist[nlos_mask], s=20, c="r", label="NLoS=1")
        axd.legend(loc="best")

    # Azimuth / elevation vs frame/time
    axang = fig.add_subplot(gs[0, 1])
    axang.set_title("UWB azimuth / elevation (deg)")
    axang.set_xlabel(x_label)
    axang.set_ylabel("Degrees")
    az_line, = axang.plot(time_axis, az, label="azimuth", alpha=0.3)
    el_line, = axang.plot(time_axis, el, label="elevation", alpha=0.3)
    az_marker, = axang.plot([], [], marker="o", linestyle="None")
    el_marker, = axang.plot([], [], marker="o", linestyle="None")
    axang.legend(loc="best")

    # Info text panel
    axinfo = fig.add_subplot(gs[1, 1])
    axinfo.axis("off")
    info_text = axinfo.text(
        0.01, 0.99, "",
        va="top", ha="left",
        fontsize=10,
        family="monospace",
    )

    # y-limits for distance & angles
    valid_d = dist[~np.isnan(dist)]
    if len(valid_d) > 0:
        axd.set_ylim(0, max(10.0, 1.1 * np.max(valid_d)))

    all_angles = np.concatenate([az[~np.isnan(az)], el[~np.isnan(el)]])
    if len(all_angles) > 0:
        amax = 1.1 * np.max(np.abs(all_angles))
        axang.set_ylim(-amax, amax)

    fig.tight_layout()

    # Estimate interval from timestamps if available
    if times is not None and len(times) > 1:
        dt = (times.iloc[1:] - times.iloc[:-1]).dt.total_seconds().to_numpy()
        # keep only finite, positive deltas
        finite = dt[np.isfinite(dt) & (dt > 0)]
        if finite.size > 0:
            median_dt = float(np.median(finite))
            base_interval_ms = max(50, int(1000 * median_dt))
        else:
            # all deltas are zero/NaN -> fallback
            base_interval_ms = 200  # ~5 FPS
    else:
        base_interval_ms = 200  # ~5 FPS

    interval_ms = int(base_interval_ms / PLAYBACK_SPEED)
    print(f"Animation interval ≈ {interval_ms} ms (base {base_interval_ms} ms)")

    n = len(df)

    def safe_fmt(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return "NaN"
        return f"{v:.2f}"

    def update(k):
        i = min(k, n - 1)

        # 3D trajectory up to frame i (other node)
        line3d.set_data(xs[: i + 1], ys[: i + 1])
        line3d.set_3d_properties(zs[: i + 1])
        current_point.set_data([xs[i]], [ys[i]])
        current_point.set_3d_properties([zs[i]])

        # distance marker
        dist_marker.set_data([time_axis[i]], [dist[i]])

        # azimuth/elevation markers
        az_marker.set_data([time_axis[i]], [az[i]])
        el_marker.set_data([time_axis[i]], [el[i]])

        # info text
        if times is not None:
            ts_str = str(times.iloc[i])
        else:
            ts_str = f"frame {frame[i]}"

        # Node_ref at origin, Node_other at (xs, ys, zs)
        lines = [
            f"Frame: {frame[i]} / {frame[-1]}",
            f"Time:  {ts_str}",
            "",
            f"{ref_name} (reference):",
            "  X,Y,Z (cm): (0.00, 0.00, 0.00)",
            "",
            f"{other_name} (relative to reference):",
            f"  X,Y,Z (cm): ({safe_fmt(xs[i])}, {safe_fmt(ys[i])}, {safe_fmt(zs[i])})",
            "",
            "UWB:",
            f"  distance between nodes: {safe_fmt(dist[i])} cm",
            f"  azimuth:                {safe_fmt(az[i])} deg",
            f"  elevation:              {safe_fmt(el[i])} deg",
            f"  NLoS flag:              {nlos[i]}",
        ]
        info_text.set_text("\n".join(lines))

        return (
            line3d,
            current_point,
            dist_marker,
            az_marker,
            el_marker,
            info_text,
            ref_point,
        )

    # keep reference so animation isn't garbage-collected
    ani = FuncAnimation(
        fig,
        update,
        frames=n,
        interval=interval_ms,
        blit=False,
        repeat=True,
    )

    plt.show()


if __name__ == "__main__":
    main()
