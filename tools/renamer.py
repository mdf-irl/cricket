import os
import re

folder = r"C:\Users\micda\OneDrive\Desktop\mm"

for filename in os.listdir(folder):
    if filename.lower().endswith(".jpg"):
        match = re.search(r"(\d+)\.jpg$", filename, re.IGNORECASE)
        if not match:
            print(f"Skipping (no trailing number): {filename}")
            continue

        original_number = int(match.group(1))
        new_number = original_number - 3

        old_path = os.path.join(folder, filename)
        new_filename = f"{new_number}.jpg"

        if new_filename.startswith("0"):
            new_filename = new_filename.lstrip("0")

        new_path = os.path.join(folder, new_filename)

        if os.path.exists(new_path):
            print(f"Skipping (already exists): {new_filename}")
            continue

        os.rename(old_path, new_path)
        print(f"Renamed: {filename} -> {new_filename}")
