"""Read-only installation check: no camera, network, mouse or key events."""
import hashlib
import os
from pathlib import Path
import struct
import sys

os.environ['QT_QPA_PLATFORM']='offscreen'
root=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root/'Source'))
model=root/'Models/gestures/hand_landmarker.task'
assert hashlib.sha256(model.read_bytes()).hexdigest()=='fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1'
assert struct.calcsize('P')==8
import cv2,numpy as np,mediapipe as mp
from mediapipe.tasks.python import BaseOptions,vision
from PyQt6.QtWidgets import QApplication
from core.room_windows_input import WindowsAPI
from core.room_media_keys import _INPUT
assert __import__('ctypes').sizeof(_INPUT)==40
app=QApplication([])
displays=WindowsAPI().displays();assert displays
with vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(model)))) as detector:
 result=detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB,data=np.zeros((360,640,3),dtype=np.uint8)))
 assert not result.hand_landmarks
print('OK: Qt, OpenCV, local hand model, Win32 ABI and display enumeration. No camera/input used.')
