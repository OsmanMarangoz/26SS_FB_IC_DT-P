"""
Tests for ROS2Camera._decode() — image decoding from sensor_msgs/Image.

These tests do NOT require ROS2 or lerobot to be installed.
They directly import the ros2_camera module and mock the message object.
"""
import sys
import os

# Direct import: add the package directory to sys.path so we can import
# ros2_camera directly without triggering the __init__.py chain
# (which would pull in lerobot).
_pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

import numpy as np
import pytest
from types import SimpleNamespace

# Import directly from the module file, not from the package
from ros2_camera import ROS2Camera, ROS2CameraConfig


def _make_msg(encoding, width, height, data, step=None):
    """Create a mock sensor_msgs/Image message."""
    channels = {"rgb8": 3, "bgr8": 3, "rgba8": 4, "bgra8": 4}.get(encoding, 3)
    if step is None:
        step = width * channels
    return SimpleNamespace(encoding=encoding, width=width, height=height,
                           step=step, data=data)


def _make_camera(w=4, h=4):
    """Create a ROS2Camera with small test dimensions."""
    return ROS2Camera(ROS2CameraConfig(width=w, height=h))


def test_decode_rgb8():
    """rgb8: 3-channel input → correct output shape and values."""
    cam = _make_camera()
    data = np.arange(48, dtype=np.uint8).tobytes()
    msg = _make_msg("rgb8", 4, 4, data)

    out = cam._decode(msg)
    assert out.shape == (4, 4, 3)
    assert out.dtype == np.uint8
    assert np.array_equal(out, np.arange(48, dtype=np.uint8).reshape(4, 4, 3))


def test_decode_rgba8():
    """rgba8: 4-channel input → alpha stripped, output is (H, W, 3)."""
    cam = _make_camera()
    data = np.arange(64, dtype=np.uint8).tobytes()
    msg = _make_msg("rgba8", 4, 4, data)

    out = cam._decode(msg)
    assert out.shape == (4, 4, 3)
    assert out.dtype == np.uint8
    expected = np.arange(64, dtype=np.uint8).reshape(4, 4, 4)[:, :, :3]
    assert np.array_equal(out, expected)


def test_decode_bgr8():
    """bgr8: BGR input → channels swapped to RGB."""
    cam = _make_camera()
    data = np.arange(48, dtype=np.uint8).tobytes()
    msg = _make_msg("bgr8", 4, 4, data)

    out = cam._decode(msg)
    assert out.shape == (4, 4, 3)
    assert out.dtype == np.uint8
    expected = np.arange(48, dtype=np.uint8).reshape(4, 4, 3)[:, :, ::-1]
    assert np.array_equal(out, expected)


def test_decode_invalid_encoding():
    """Invalid encoding → ValueError."""
    cam = _make_camera()
    msg = _make_msg("yuv422", 4, 4, b"\x00" * 48)
    with pytest.raises(ValueError):
        cam._decode(msg)


def test_decode_stride_padding():
    """Row stride with padding bytes → padding ignored, correct output."""
    cam = _make_camera()
    # 4x4 rgb8 with 4 bytes padding per row. Step = 12 + 4 = 16.
    # Total data size = 4 rows * 16 bytes = 64 bytes
    data_array = np.zeros((4, 16), dtype=np.uint8)
    for i in range(4):
        data_array[i, :12] = np.arange(i * 12, (i + 1) * 12, dtype=np.uint8)
    data = data_array.tobytes()
    msg = _make_msg("rgb8", 4, 4, data, step=16)

    out = cam._decode(msg)
    assert out.shape == (4, 4, 3)
    expected = np.arange(48, dtype=np.uint8).reshape(4, 4, 3)
    assert np.array_equal(out, expected)
