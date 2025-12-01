import pandas as pd
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np

# Load Data
df = pd.read_csv('combined_global_coords.csv')

fig = plt.figure(figsize=(10, 8))
ax = fig.add_subplot(111, projection='3d')

# 1. Plot Pi Zero (Reference)
ax.scatter([0], [0], [0], c='red', marker='^', s=200, label='Pi Zero (Ref)')

# 2. Plot Pi One (Estimates & Mean)
# The "Cloud" of all estimates
ax.scatter(df['PiOne_Global_X'], df['PiOne_Global_Y'], df['PiOne_Global_Z'], 
           c='blue', alpha=0.1, label='Pi One (Noise)')
# The Mean Position
mx, my, mz = df['PiOne_Global_X'].mean(), df['PiOne_Global_Y'].mean(), df['PiOne_Global_Z'].mean()
ax.scatter([mx], [my], [mz], c='blue', marker='^', s=200, label='Pi One (Mean)')

# 3. Plot Tag Trajectory
sc = ax.scatter(df['Global_Target_X'], df['Global_Target_Y'], df['Global_Target_Z'], 
                c=range(len(df)), cmap='viridis', label='Tag Path')

# Formatting
ax.set_xlabel('X (cm)')
ax.set_ylabel('Y (cm)')
ax.set_zlabel('Z (cm)')
ax.legend()
plt.title("Pi Zero vs Pi One Positioning")

plt.show()