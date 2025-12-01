#!/usr/bin/env python3
"""
Analyze two node*_frames.csv files:

- Convert UWB spherical (distance_cm, azimuth_deg, elevation_deg) to
  Cartesian X,Y,Z in cm for each node.
- Compute change in IMU heading/pitch (deg) relative to the first frame.
- Compute change in UWB azimuth/elevation (deg) relative to the first frame.
- Compute approximate distance between the two nodes in cm.
- Save everything to cartesian_debug.csv and print a small summary.

Usage (from folder with node1_frames.csv, node2_frames.csv):

    python analyze_cartesian_debug.py
or:

    python analyze_cartesian_debug.py --node1 node1_frames.csv \
                                      --node2 node2_frames.csv \
                                      --out cartesian_debug.csv
"""

import argparse
import math
import numpy as np
import pandas as pd


def spherical_to_cartesian(dist_cm, az_deg, el_deg):
    """
    Convert spherical (distance, azimuth, elevation) to Cartesian (x, y, z).

    dist_cm : radius in cm
    az_deg  : azimuth in degrees (0 = +X axis, CCW towards +Y)
    el_deg  : elevation in degrees (0 = XY plane, +Z up)
    """
    if pd.isna(dist_cm) or pd.isna(az_deg) or pd.isna(el_deg):
        return (np.nan, np.nan, np.nan)

    r = float(dist_cm)
    az = math.radians(float(az_deg))
    el = math.radians(float(el_deg))

    x = r * math.cos(el) * math.cos(az)
    y = r * math.cos(el) * math.sin(az)
    z = r * math.sin(el)
    return x, y, z


def angle_diff_deg(a, b):
    """
    Smallest signed difference a-b in degrees in [-180, 180].
    Returns NaN if either is NaN.
    """
    if pd.isna(a) or pd.isna(b):
        return np.nan
    a = float(a)
    b = float(b)
    d = (a - b + 180.0) % 360.0 - 180.0
    return d


def build_parser():
    p = argparse.ArgumentParser(description="Convert UWB to Cartesian and summarize IMU/UWB changes.")
    p.add_argument("--node1", default="node1_frames.csv",
                   help="CSV for node 1 (default: node1_frames.csv)")
    p.add_argument("--node2", default="node2_frames.csv",
                   help="CSV for node 2 (default: node2_frames.csv)")
    p.add_argument("--out", default="cartesian_debug.csv",
                   help="Output CSV with Cartesian + deltas (default: cartesian_debug.csv)")
    return p


def main():
    args = build_parser().parse_args()

    # Load both CSVs
    df1 = pd.read_csv(args.node1)
    df2 = pd.read_csv(args.node2)

    # Merge by frame_index so we have one row per paired frame
    df = df1.merge(df2, on="frame_index", suffixes=("_n1", "_n2"))

    # Baseline IMU + UWB angles (first non-NaN for each node)
    base_h1 = df["imu_heading_deg_n1"].dropna().iloc[0]
    base_p1 = df["imu_pitch_deg_n1"].dropna().iloc[0]
    base_h2 = df["imu_heading_deg_n2"].dropna().iloc[0]
    base_p2 = df["imu_pitch_deg_n2"].dropna().iloc[0]

    base_az1 = df["uwb_azimuth_deg_n1"].dropna().iloc[0]
    base_el1 = df["uwb_elevation_deg_n1"].dropna().iloc[0]
    base_az2 = df["uwb_azimuth_deg_n2"].dropna().iloc[0]
    base_el2 = df["uwb_elevation_deg_n2"].dropna().iloc[0]

    x1_list, y1_list, z1_list = [], [], []
    x2_list, y2_list, z2_list = [], [], []
    dist_list = []

    dhead1_list, dpitch1_list = [], []
    dhead2_list, dpitch2_list = [], []

    daz1_list, del1_list = [], []
    daz2_list, del2_list = [], []

    for _, r in df.iterrows():
        # Cartesian positions from UWB
        x1, y1, z1 = spherical_to_cartesian(
            r["uwb_distance_cm_n1"], r["uwb_azimuth_deg_n1"], r["uwb_elevation_deg_n1"]
        )
        x2, y2, z2 = spherical_to_cartesian(
            r["uwb_distance_cm_n2"], r["uwb_azimuth_deg_n2"], r["uwb_elevation_deg_n2"]
        )

        x1_list.append(x1)
        y1_list.append(y1)
        z1_list.append(z1)

        x2_list.append(x2)
        y2_list.append(y2)
        z2_list.append(z2)

        if not any(pd.isna(v) for v in (x1, y1, z1, x2, y2, z2)):
            dx = x1 - x2
            dy = y1 - y2
            dz = z1 - z2
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        else:
            dist = np.nan
        dist_list.append(dist)

        # IMU heading/pitch deltas
        dhead1_list.append(angle_diff_deg(r["imu_heading_deg_n1"], base_h1))
        dpitch1_list.append(angle_diff_deg(r["imu_pitch_deg_n1"], base_p1))
        dhead2_list.append(angle_diff_deg(r["imu_heading_deg_n2"], base_h2))
        dpitch2_list.append(angle_diff_deg(r["imu_pitch_deg_n2"], base_p2))

        # UWB azimuth/elevation deltas
        daz1_list.append(angle_diff_deg(r["uwb_azimuth_deg_n1"], base_az1))
        del1_list.append(angle_diff_deg(r["uwb_elevation_deg_n1"], base_el1))
        daz2_list.append(angle_diff_deg(r["uwb_azimuth_deg_n2"], base_az2))
        del2_list.append(angle_diff_deg(r["uwb_elevation_deg_n2"], base_el2))

    # Build output dataframe
    out = pd.DataFrame({
        "frame_index": df["frame_index"],

        # Cartesian coords (cm)
        "node1_x_cm": x1_list,
        "node1_y_cm": y1_list,
        "node1_z_cm": z1_list,
        "node2_x_cm": x2_list,
        "node2_y_cm": y2_list,
        "node2_z_cm": z2_list,

        # Approx distance between nodes (cm)
        "distance_between_cm": dist_list,

        # IMU heading/pitch + deltas
        "node1_heading_deg": df["imu_heading_deg_n1"],
        "node1_dheading_deg": dhead1_list,
        "node1_pitch_deg": df["imu_pitch_deg_n1"],
        "node1_dpitch_deg": dpitch1_list,

        "node2_heading_deg": df["imu_heading_deg_n2"],
        "node2_dheading_deg": dhead2_list,
        "node2_pitch_deg": df["imu_pitch_deg_n2"],
        "node2_dpitch_deg": dpitch2_list,

        # UWB angles + deltas
        "node1_azimuth_deg": df["uwb_azimuth_deg_n1"],
        "node1_dazimuth_deg": daz1_list,
        "node1_elevation_deg": df["uwb_elevation_deg_n1"],
        "node1_delevation_deg": del1_list,

        "node2_azimuth_deg": df["uwb_azimuth_deg_n2"],
        "node2_dazimuth_deg": daz2_list,
        "node2_elevation_deg": df["uwb_elevation_deg_n2"],
        "node2_delevation_deg": del2_list,
    })

    # Save full table to CSV for deeper inspection
    out.to_csv(args.out, index=False)
    print(f"\n[INFO] Wrote detailed Cartesian + IMU/UWB deltas to: {args.out}")

    # Print a compact view to the terminal (just to "see" the numbers)
    cols_to_show = [
        "frame_index",
        "node1_x_cm", "node1_y_cm", "node1_z_cm",
        "node2_x_cm", "node2_y_cm", "node2_z_cm",
        "distance_between_cm",
        "node1_dheading_deg", "node1_dpitch_deg",
        "node2_dheading_deg", "node2_dpitch_deg",
        "node1_dazimuth_deg", "node1_delevation_deg",
        "node2_dazimuth_deg", "node2_delevation_deg",
    ]

    print("\n[INFO] First 10 frames (Cartesian coords + changes):\n")
    print(out[cols_to_show].head(10).to_string(index=False))

    print("\n[INFO] Last 10 frames:\n")
    print(out[cols_to_show].tail(10).to_string(index=False))

    # Simple stats on distance
    valid_d = out["distance_between_cm"].dropna()
    if len(valid_d) > 0:
        print("\n[INFO] Distance between nodes (cm):")
        print(f"  min    = {valid_d.min():.2f}")
        print(f"  max    = {valid_d.max():.2f}")
        print(f"  median = {valid_d.median():.2f}")
    else:
        print("\n[WARN] No valid distance samples (NaNs in UWB).")


if __name__ == "__main__":
    main()
