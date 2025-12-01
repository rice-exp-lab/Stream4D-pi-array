import pandas as pd
import numpy as np

def process_uwb_fusion():
    # 1. Load the raw files
    # Make sure these filenames match exactly what is in your folder
    try:
        df0 = pd.read_csv('0-Setup-Hardware\output\pi_zero_uwb_data.csv')
        df1 = pd.read_csv('0-Setup-Hardware\output\pi_one_uwb_data.csv')
    except FileNotFoundError as e:
        print(f"Error: Could not find file. {e}")
        return

    # 2. Convert text timestamps to datetime objects for synchronization
    # Adding a dummy date because the file only has times
    df0['dt'] = pd.to_datetime(df0['Timestamp'], format='%H:%M:%S.%f')
    df1['dt'] = pd.to_datetime(df1['Timestamp'], format='%H:%M:%S.%f')

    # 3. Function to convert Range/Azimuth/Elevation -> X/Y/Z
    def add_xyz_cols(df, suffix):
        # Convert degrees to radians
        az = np.radians(df['Azimuth_deg'])
        el = np.radians(df['Elevation_deg'])
        r = df['Distance_cm']
        
        # Calculate Cartesian Coordinates
        # X = Forward, Y = Left/Right, Z = Up/Down
        x = r * np.cos(el) * np.cos(az)
        y = r * np.cos(el) * np.sin(az)
        z = r * np.sin(el)
        
        df[f'x_{suffix}'] = x
        df[f'y_{suffix}'] = y
        df[f'z_{suffix}'] = z
        return df

    # Apply conversion to both datasets
    df0 = add_xyz_cols(df0, 'p0') # p0 = Pi Zero
    df1 = add_xyz_cols(df1, 'p1') # p1 = Pi One

    # 4. Synchronize the data (Merge Nearest Neighbors)
    df0 = df0.sort_values('dt')
    df1 = df1.sort_values('dt')
    
    # Match Pi One rows to the closest Pi Zero timestamp (within 100ms)
    # Suffixes will rename 'Timestamp' to 'Timestamp_zero' and 'Timestamp_one'
    merged = pd.merge_asof(
        df0, df1, 
        on='dt', 
        direction='nearest', 
        tolerance=pd.Timedelta('100ms'), 
        suffixes=('_zero', '_one')
    )
    
    # Drop rows where synchronization failed
    merged = merged.dropna(subset=['x_p1'])

    # --- FIX START ---
    # Restore the main 'Timestamp' column using the Pi Zero time
    merged['Timestamp'] = merged['Timestamp_zero']
    # --- FIX END ---

    # 5. Calculate Global Coordinates
    # DEFINITION: Global Origin (0,0,0) is Pi Zero.
    # Therefore, the Target's Global Position is exactly what Pi Zero sees.
    merged['Global_Target_X'] = merged['x_p0']
    merged['Global_Target_Y'] = merged['y_p0']
    merged['Global_Target_Z'] = merged['z_p0']

    # 6. Estimate Pi One's Location
    # Assuming sensors are parallel: PiOne_Pos = Target_Pos - PiOne_View_of_Target
    merged['PiOne_Global_X'] = merged['x_p0'] - merged['x_p1']
    merged['PiOne_Global_Y'] = merged['y_p0'] - merged['y_p1']
    merged['PiOne_Global_Z'] = merged['z_p0'] - merged['z_p1']

    # 7. Save to CSV
    output_filename = 'combined_global_coords.csv'
    cols_to_save = [
        'Timestamp', 
        'Global_Target_X', 'Global_Target_Y', 'Global_Target_Z', 
        'PiOne_Global_X', 'PiOne_Global_Y', 'PiOne_Global_Z'
    ]
    
    merged[cols_to_save].to_csv(output_filename, index=False)
    
    print(f"File saved: {output_filename}")
    print("Coordinates of Pi One (Mean Estimate):")
    print(merged[['PiOne_Global_X', 'PiOne_Global_Y', 'PiOne_Global_Z']].mean())

if __name__ == "__main__":
    process_uwb_fusion()