import json
import tkinter as tk
from tkinter import filedialog

def shift_coordinates(filename=None):
    """
    Center (and later scale) the coordinates in a system JSON file.
    If `filename` is provided, operates directly on that file;
    otherwise, prompts the user to select one.
    """
    # File dialog
    if not filename:
        root = tk.Tk()
        root.withdraw()
        filename = filedialog.askopenfilename(
            title="Select system JSON file",
            filetypes=[("JSON files", "*.json")]
        )
        if not filename:
            print("No file selected.")
            return

    with open(filename, 'r') as f:
        data = json.load(f)

    coords = []

    # Collect coordinates from objects
    for obj in data.get("objects", {}).values():
        if "coordinate" in obj:
            coords.append(obj["coordinate"])

    # Sensor relays
    for relay in data.get("sensor_relay", {}).values():
        if "coordinate" in relay:
            coords.append(relay["coordinate"])

    # Terrain start/end points
    for terrain in data.get("terrain", {}).values():
        if "start" in terrain:
            coords.append(terrain["start"])
        if "end" in terrain:
            coords.append(terrain["end"])

    if not coords:
        print("No coordinates found to center.")
        return

    # Compute center offset
    xs, ys, zs = zip(*coords)
    offset_x = (min(xs) + max(xs)) / 2
    offset_y = (min(ys) + max(ys)) / 2
    offset_z = (min(zs) + max(zs)) / 2

    def shift(coord):
        return [
            coord[0] - offset_x,
            coord[1] - offset_y,
            coord[2] - offset_z
        ]

    # Apply shifts
    for obj in data.get("objects", {}).values():
        if "coordinate" in obj:
            obj["coordinate"] = shift(obj["coordinate"])

    for relay in data.get("sensor_relay", {}).values():
        if "coordinate" in relay:
            relay["coordinate"] = shift(relay["coordinate"])

    for terrain in data.get("terrain", {}).values():
        if "start" in terrain:
            terrain["start"] = shift(terrain["start"])
        if "end" in terrain:
            terrain["end"] = shift(terrain["end"])

    # DO NOT change systemMapCoord
    # (deliberately skipped)

    # Overwrite the original file
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

    print(f"File centered and saved back to: {filename}")

if __name__ == "__main__":
    shift_coordinates()
