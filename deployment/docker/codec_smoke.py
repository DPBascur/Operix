"""Prueba sintética de codec; no abre videos, modelos ni datasets."""
from pathlib import Path
import tempfile

import cv2
import numpy as np

with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / "synthetic.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"avc1"), 30, (64, 64))
    if not writer.isOpened():
        raise RuntimeError("OpenCV requiere un encoder H.264/avc1 operativo")
    for _ in range(3):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()
    capture = cv2.VideoCapture(str(path))
    frames = 0
    while capture.read()[0]:
        frames += 1
    capture.release()
    if frames != 3:
        raise RuntimeError("El MP4 sintético no se decodifica completo")
print("OpenCV avc1 encode/decode: PASS")
