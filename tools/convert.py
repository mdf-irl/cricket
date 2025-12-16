import subprocess
import os
import sys

# ====== CONFIG ======
PDF_FILE = "input.pdf"          # Path to your PDF
OUTPUT_PREFIX = "page"          # page-1.jpg, page-2.jpg, etc.
DPI = 300                       # High quality
POPPLER_BIN = r"C:\poppler\poppler-25.12.0\Library\bin"  # Path containing pdftocairo.exe
# ====================

pdftocairo = os.path.join(POPPLER_BIN, "pdftocairo.exe")

if not os.path.exists(pdftocairo):
    print("ERROR: pdftocairo.exe not found")
    sys.exit(1)

if not os.path.exists(PDF_FILE):
    print("ERROR: PDF file not found")
    sys.exit(1)

command = [
    pdftocairo,
    "-jpeg",
    "-r", str(DPI),
    PDF_FILE,
    OUTPUT_PREFIX
]

print("Converting PDF to JPGs...")
subprocess.run(command, check=True)

print("Done.")
