import json

def scale_system(filename, scale):
    """
    Scale all coordinate values in the system JSON file by the given multiplier.
    - filename: path to the JSON file.
    - scale: float multiplier (e.g. 10 to enlarge 10×, 0.5 to shrink by half).
    """
    # Load the existing system
    with open(filename, 'r') as f:
        data = json.load(f)

    # Helper to scale a coordinate list
    def s(coord_list):
        return [c * scale for c in coord_list]

    # Scale object coordinates
    for obj in data.get("objects", {}).values():
        if "coordinate" in obj and isinstance(obj["coordinate"], list):
            obj["coordinate"] = s(obj["coordinate"])

    # Scale sensor relay coordinates
    for relay in data.get("sensor_relay", {}).values():
        if "coordinate" in relay and isinstance(relay["coordinate"], list):
            relay["coordinate"] = s(relay["coordinate"])

    # Scale terrain start/end points
    for terrain in data.get("terrain", {}).values():
        if "start" in terrain and isinstance(terrain["start"], list):
            terrain["start"] = s(terrain["start"])
        if "end" in terrain and isinstance(terrain["end"], list):
            terrain["end"] = s(terrain["end"])

    # (If you have other coordinate‐based sections, apply the same pattern.)

    # Write back the scaled system
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

    print(f"File '{filename}' scaled by factor {scale} and saved.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python ResizeTool.py <path/to/system.json> <scale>")
    else:
        fname, factor = sys.argv[1], float(sys.argv[2])
        scale_system(fname, factor)