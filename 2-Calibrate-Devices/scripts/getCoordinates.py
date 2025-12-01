import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
from math import radians, cos, sin, sqrt
from datetime import datetime
import time

# ========= USER CONFIG =========
NODE1_CSV = "2-Calibrate-Devices/output/session_node1/node1_frames.csv"
NODE2_CSV = "2-Calibrate-Devices/output/session_node2/node2_frames.csv"
# 1.0 = approx real-time (based on timestamps)
# >1.0 = faster playback, <1.0 = slower
PLAYBACK_SPEED = 1.0
# ===============================


def parse_time(ts):
    if pd.isna(ts):
        return None
    try:
        return datetime.fromisoformat(str(ts))
    except Exception:
        return None


def spherical_to_cartesian(dist_cm, az_deg, el_deg):
    """
    Convert spherical (distance, azimuth, elevation) to Cartesian (x, y, z).

    dist_cm : radius in cm
    az_deg  : azimuth in degrees (0 = +X, CCW towards +Y)
    el_deg  : elevation in degrees (0 = XY plane, +Z up)
    """
    r = float(dist_cm)
    az = radians(float(az_deg))
    el = radians(float(el_deg))

    x = r * cos(el) * cos(az)
    y = r * cos(el) * sin(az)
    z = r * sin(el)
    return x, y, z


def orientation_vector_from_imu(heading_deg, pitch_deg):
    """
    Compute a simple 3D orientation vector from IMU heading (yaw) and pitch.
    Roll is ignored here.
    """
    if heading_deg is None or pitch_deg is None:
        return None
    try:
        yaw = radians(float(heading_deg))
        pitch = radians(float(pitch_deg))
    except Exception:
        return None

    vx = cos(pitch) * cos(yaw)
    vy = cos(pitch) * sin(yaw)
    vz = sin(pitch)
    return vx, vy, vz


def safe_val(val):
    if val is None:
        return "None"
    if isinstance(val, (float, int)):
        if np.isnan(val):
            return "NaN"
        return f"{val:.2f}"
    return str(val)


def main():
    # ---- Load CSVs ----
    df1 = pd.read_csv(NODE1_CSV)
    df2 = pd.read_csv(NODE2_CSV)

    # Make sure both have the same number of frames
    n = min(len(df1), len(df2))
    df1 = df1.iloc[:n].reset_index(drop=True)
    df2 = df2.iloc[:n].reset_index(drop=True)

    # ---- Build a time axis from timestamps ----
    t1 = df1["img_timestamp_iso"].apply(parse_time)
    t2 = df2["img_timestamp_iso"].apply(parse_time)

    times = []
    for a, b in zip(t1, t2):
        if a and b:
            times.append(min(a, b))
        elif a:
            times.append(a)
        else:
            times.append(b)

    # Estimate frame interval from timestamps
    if len(times) > 1:
        deltas = [(times[i + 1] - times[i]).total_seconds()
                  for i in range(len(times) - 1)]
        median_dt = float(np.median(deltas))
        base_interval = max(0.05, median_dt)  # seconds
    else:
        base_interval = 1.0

    step_interval = base_interval / PLAYBACK_SPEED
    print(f"Loaded {n} paired frames.")
    print(f"Estimated frame interval: {base_interval:.3f} s, "
          f"playback interval: {step_interval:.3f} s")

    # ---- Precompute positions and distances ----
    positions1 = []
    positions2 = []
    node_distance = []

    # For export
    export_rows = []

    for i in range(n):
        row1 = df1.iloc[i]
        row2 = df2.iloc[i]

        # Node 1 position
        p1 = None
        if (not np.isnan(row1["uwb_distance_cm"])
                and not np.isnan(row1["uwb_azimuth_deg"])
                and not np.isnan(row1["uwb_elevation_deg"])):
            p1 = spherical_to_cartesian(
                row1["uwb_distance_cm"],
                row1["uwb_azimuth_deg"],
                row1["uwb_elevation_deg"],
            )

        # Node 2 position
        p2 = None
        if (not np.isnan(row2["uwb_distance_cm"])
                and not np.isnan(row2["uwb_azimuth_deg"])
                and not np.isnan(row2["uwb_elevation_deg"])):
            p2 = spherical_to_cartesian(
                row2["uwb_distance_cm"],
                row2["uwb_azimuth_deg"],
                row2["uwb_elevation_deg"],
            )

        positions1.append(p1)
        positions2.append(p2)

        if p1 is not None and p2 is not None:
            dx = p1[0] - p2[0]
            dy = p1[1] - p2[1]
            dz = p1[2] - p2[2]
            d = sqrt(dx * dx + dy * dy + dz * dz)
        else:
            d = float("nan")
        node_distance.append(d)

        # For CSV export: collect coordinates + distance
        export_rows.append({
            "frame_index": i + 1,
            "time_node1": df1.loc[i, "img_timestamp_iso"],
            "time_node2": df2.loc[i, "img_timestamp_iso"],
            "node1_x_cm": p1[0] if p1 is not None else np.nan,
            "node1_y_cm": p1[1] if p1 is not None else np.nan,
            "node1_z_cm": p1[2] if p1 is not None else np.nan,
            "node2_x_cm": p2[0] if p2 is not None else np.nan,
            "node2_y_cm": p2[1] if p2 is not None else np.nan,
            "node2_z_cm": p2[2] if p2 is not None else np.nan,
            "distance_cm": d,
        })

    # ---- Save XYZ + distance to a new CSV ----
    export_df = pd.DataFrame(export_rows)
    export_df.to_csv("paired_coordinates.csv", index=False)
    print("Saved XYZ + distance data to paired_coordinates.csv")

    # ---- Set up Matplotlib figure (loop-based playback) ----
    plt.ion()
    fig = plt.figure(figsize=(12, 6))
    gs = fig.add_gridspec(2, 2, height_ratios=[2, 1])

    ax3d = fig.add_subplot(gs[0, 0], projection="3d")
    ax3d.set_title("3D positions (UWB)")
    ax3d.set_xlabel("X (cm)")
    ax3d.set_ylabel("Y (cm)")
    ax3d.set_zlabel("Z (cm)")

    ax_dist = fig.add_subplot(gs[1, :])
    ax_dist.set_title("Distance between nodes (cm)")
    ax_dist.set_xlabel("Frame index")
    ax_dist.set_ylabel("Distance (cm)")

    ax_info = fig.add_subplot(gs[0, 1])
    ax_info.axis("off")
    info_text = ax_info.text(
        0.01,
        0.99,
        "",
        va="top",
        ha="left",
        fontsize=10,
        family="monospace",
    )

    # Precompute axis limits from all positions
    all_coords = []
    for p in positions1 + positions2:
        if p is not None:
            all_coords.extend(p)

    if all_coords:
        max_abs = max(abs(float(c)) for c in all_coords)
        max_abs = max(max_abs, 10.0)
    else:
        max_abs = 10.0

    ax3d.set_xlim(-max_abs, max_abs)
    ax3d.set_ylim(-max_abs, max_abs)
    ax3d.set_zlim(-max_abs, max_abs)

    dist_line, = ax_dist.plot([], [], lw=2)

    print("Close the window or press Ctrl+C to stop.")

    try:
        for frame in range(n):
            ax3d.cla()
            ax3d.set_title("3D positions (UWB)")
            ax3d.set_xlabel("X (cm)")
            ax3d.set_ylabel("Y (cm)")
            ax3d.set_zlabel("Z (cm)")
            ax3d.set_xlim(-max_abs, max_abs)
            ax3d.set_ylim(-max_abs, max_abs)
            ax3d.set_zlim(-max_abs, max_abs)

            p1 = positions1[frame]
            p2 = positions2[frame]

            # Node 1
            if p1 is not None:
                ax3d.scatter([p1[0]], [p1[1]], [p1[2]], c="r", s=40, label="node1")
                h1 = df1.loc[frame, "imu_heading_deg"]
                pitch1 = df1.loc[frame, "imu_pitch_deg"]
                v1 = orientation_vector_from_imu(h1, pitch1)
                if v1 is not None:
                    ax3d.quiver(
                        p1[0], p1[1], p1[2],
                        v1[0], v1[1], v1[2],
                        length=0.3 * max_abs,
                        normalize=True,
                        color="r",
                    )

            # Node 2
            if p2 is not None:
                ax3d.scatter([p2[0]], [p2[1]], [p2[2]], c="b", s=40, label="node2")
                h2 = df2.loc[frame, "imu_heading_deg"]
                pitch2 = df2.loc[frame, "imu_pitch_deg"]
                v2 = orientation_vector_from_imu(h2, pitch2)
                if v2 is not None:
                    ax3d.quiver(
                        p2[0], p2[1], p2[2],
                        v2[0], v2[1], v2[2],
                        length=0.3 * max_abs,
                        normalize=True,
                        color="b",
                    )

            ax3d.legend(loc="upper right")

            # Distance plot
            x_data = np.arange(frame + 1)
            y_data = node_distance[: frame + 1]
            dist_line.set_data(x_data, y_data)
            ax_dist.set_xlim(0, n)

            valid_d = [d for d in node_distance if not np.isnan(d)]
            if valid_d:
                max_d = max(valid_d)
                ax_dist.set_ylim(0, max(max_d * 1.1, 10))
            else:
                ax_dist.set_ylim(0, 10)

            # Info panel text (including XYZ coordinates)
            row1 = df1.iloc[frame]
            row2 = df2.iloc[frame]
            d = node_distance[frame]

            lines = []
            lines.append(f"Frame {frame+1}/{n}")
            lines.append("")
            lines.append("Node 1:")
            lines.append(f"  img_ts: {row1['img_timestamp_iso']}")
            lines.append(f"  UWB dist: {safe_val(row1['uwb_distance_cm'])} cm")
            lines.append(
                f"  UWB az/el: {safe_val(row1['uwb_azimuth_deg'])} / "
                f"{safe_val(row1['uwb_elevation_deg'])} deg"
            )
            if p1 is not None:
                lines.append(
                    f"  XYZ (cm): ({safe_val(p1[0])}, "
                    f"{safe_val(p1[1])}, {safe_val(p1[2])})"
                )
            else:
                lines.append("  XYZ (cm): None")
            lines.append(
                f"  IMU heading/pitch: "
                f"{safe_val(row1['imu_heading_deg'])} / "
                f"{safe_val(row1['imu_pitch_deg'])} deg"
            )
            lines.append("")
            lines.append("Node 2:")
            lines.append(f"  img_ts: {row2['img_timestamp_iso']}")
            lines.append(f"  UWB dist: {safe_val(row2['uwb_distance_cm'])} cm")
            lines.append(
                f"  UWB az/el: {safe_val(row2['uwb_azimuth_deg'])} / "
                f"{safe_val(row2['uwb_elevation_deg'])} deg"
            )
            if p2 is not None:
                lines.append(
                    f"  XYZ (cm): ({safe_val(p2[0])}, "
                    f"{safe_val(p2[1])}, {safe_val(p2[2])})"
                )
            else:
                lines.append("  XYZ (cm): None")
            lines.append(
                f"  IMU heading/pitch: "
                f"{safe_val(row2['imu_heading_deg'])} / "
                f"{safe_val(row2['imu_pitch_deg'])} deg"
            )
            lines.append("")
            lines.append(f"Inter-node distance: {safe_val(d)} cm")

            info_text.set_text("\n".join(lines))
            fig.suptitle("3D Playback from IMU + UWB CSVs", fontsize=14)

            plt.pause(step_interval)

    except KeyboardInterrupt:
        print("\nInterrupted by user.")

    plt.ioff()
    plt.show()


if __name__ == "__main__":
    main()
