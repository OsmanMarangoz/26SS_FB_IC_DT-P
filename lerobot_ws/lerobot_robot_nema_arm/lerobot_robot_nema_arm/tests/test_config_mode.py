"""
Tests for NemaArmConfig and NemaArm mode switching.

These tests do NOT require ROS2 to be installed.
They verify that mode selection correctly configures camera backends
and observation features.
"""
import sys
import os

# Direct import: add the package directory to sys.path so we can import
# modules directly without triggering the __init__.py chain
# (which would pull in lerobot).
_pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

import pytest

# We need to mock lerobot before importing our modules
from unittest.mock import MagicMock

# Create minimal lerobot mock so config_nema_arm and nema_arm can import
_lerobot_mock = MagicMock()


class _FakeRobotConfig:
    @classmethod
    def register_subclass(cls, name):
        return lambda c: c


class _FakeRobot:
    def __init__(self, config):
        pass


_lerobot_mock.robots.RobotConfig = _FakeRobotConfig
_lerobot_mock.robots.Robot = _FakeRobot

sys.modules["lerobot"] = _lerobot_mock
sys.modules["lerobot.robots"] = _lerobot_mock.robots

# Now import our modules
from config_nema_arm import NemaArmConfig
from nema_arm import NemaArm


def test_twin_mode_uses_unity_topics():
    """Twin mode cameras dict should contain /unity/ topic paths."""
    config = NemaArmConfig(mode="twin")
    assert len(config.cameras) == 2
    for topic in config.cameras.values():
        assert "/unity/" in str(topic)


def test_real_mode_does_not_use_unity_topics():
    """Real mode cameras dict should NOT contain /unity/ topic paths."""
    config = NemaArmConfig(mode="real")
    for value in config.cameras.values():
        assert "/unity/" not in str(value)


def test_no_camera_disables_images():
    """use_camera=False → no image features (no tuples in observation_features)."""
    config = NemaArmConfig(use_camera=False)
    robot = NemaArm(config)
    for feat_name, feat_type in robot.observation_features.items():
        assert not isinstance(feat_type, tuple), (
            f"Expected no image features, but found {feat_name}={feat_type}"
        )


def test_twin_mode_image_features():
    """Twin mode → observation_features contain cam_top and cam_side with correct shape."""
    config = NemaArmConfig(mode="twin")
    robot = NemaArm(config)

    features = robot.observation_features
    assert "cam_top" in features, f"cam_top missing. Features: {list(features.keys())}"
    assert "cam_side" in features, f"cam_side missing. Features: {list(features.keys())}"
    assert features["cam_top"] == (480, 640, 3)
    assert features["cam_side"] == (480, 640, 3)


def test_twin_mode_camera_count():
    """Twin mode → exactly 2 cameras created."""
    config = NemaArmConfig(mode="twin")
    robot = NemaArm(config)
    assert len(robot.cameras) == 2


def test_real_mode_camera_count():
    """Real mode with default config → exactly 1 camera (cam_top only)."""
    config = NemaArmConfig(mode="real")
    robot = NemaArm(config)
    assert len(robot.cameras) == 1
    assert "cam_top" in robot.cameras


def test_invalid_mode_raises():
    """Invalid mode → ValueError."""
    with pytest.raises(ValueError):
        NemaArmConfig(mode="invalid")


def test_no_camera_empty_cameras_dict():
    """use_camera=False → cameras dict is empty."""
    config = NemaArmConfig(use_camera=False)
    robot = NemaArm(config)
    assert len(robot.cameras) == 0
