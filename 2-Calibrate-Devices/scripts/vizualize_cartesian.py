import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
import math

# -------- USER CONFIG --------
REFERENCE_NODE = 2   # 1 or 2: which node's UWB you want to trust for geometry
NODE1_CSV = "2-Calibrate-Devices/output/session_node1/node1_frames.csv"
NODE2_CSV = "2-Calibrate-Devices/output/session_node2/node2_frames.csv"
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
    else:
        df = df2
        label = "node2 (reference)"

    frame = df["frame_index"]
    dist = df["uwb_distance_cm"]
    az   = df["uwb_azimuth_deg"]
    el   = df["uwb_elevation_deg"]
    nlos = df["uwb_nlos_status"]

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

    # ---------- Make plots ----------
    plt.figure(figsize=(14, 8))
    gs = plt.GridSpec(2, 2, height_ratios=[2, 1])

    # 3D track (this node's view of the other node)
    ax3d = plt.subplot(gs[0, 0], projection="3d")
    ax3d.set_title(f"Relative 3D position from {label}")
    ax3d.set_xlabel("X (cm)")
    ax3d.set_ylabel("Y (cm)")
    ax3d.set_zlabel("Z (cm)")
    ax3d.plot(xs, ys, zs, marker="o")

    # symmetric axis limits
    valid = np.concatenate([xs[~np.isnan(xs)], ys[~np.isnan(ys)], zs[~np.isnan(zs)]])
    if len(valid) > 0:
        m = max(np.max(np.abs(valid)), 10.0)
        ax3d.set_xlim(-m, m)
        ax3d.set_ylim(-m, m)
        ax3d.set_zlim(-m, m)

    # Distance vs frame
    axd = plt.subplot(gs[0, 1])
    axd.set_title("UWB distance (this node's range)")
    axd.set_xlabel("Frame index")
    axd.set_ylabel("Distance (cm)")
    axd.plot(frame, dist, marker="o")
    # mark NLoS
    axd.scatter(frame[nlos == 1], dist[nlos == 1], c="r", s=20, label="NLoS=1")
    axd.legend(loc="best")

    # Azimuth / elevation vs frame
    axang = plt.subplot(gs[1, :])
    axang.set_title("UWB azimuth / elevation (deg)")
    axang.set_xlabel("Frame index")
    axang.set_ylabel("Degrees")
    axang.plot(frame, az, label="azimuth")
    axang.plot(frame, el, label="elevation")
    axang.legend(loc="best")

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
