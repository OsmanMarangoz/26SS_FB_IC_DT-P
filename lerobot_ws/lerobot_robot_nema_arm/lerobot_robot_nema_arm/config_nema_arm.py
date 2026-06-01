from dataclasses import dataclass, field
from lerobot.robots import RobotConfig


@RobotConfig.register_subclass("nema_arm")
@dataclass
class NemaArmConfig(RobotConfig):
    """
    Configuration für den 4-DOF NEMA Stepper Arm.

    Topics (aus README Section 3.2 — NICHT ändern):
        /joint_states        ← stm32_serial_node publisht hier (200 Hz, 7 joints)
        /planned_trajectory  ← unity_moveit_bridge publisht hier
        /stm32_cmd           ← unity_moveit_bridge publisht hier
    """

    # ── ROS2 Topics ───────────────────────────────────────────────────────
    joint_states_topic: str = "/joint_states"
    planned_trajectory_topic: str = "/planned_trajectory"
    stm32_cmd_topic: str = "/stm32_cmd"

    # ── Arm Joints (Motor 1-4) ────────────────────────────────────────────
    arm_joints: list = field(default_factory=lambda: [
        "joint_basis_arm1",
        "joint_arm1_arm2",
        "joint_arm2_arm3",
        "joint_arm3_greifer",
    ])

    # ── Finger Joints (Motor 5, interpoliert) ─────────────────────────────
    finger_joints: list = field(default_factory=lambda: [
        "joint_greifer_finger1",
        "joint_greifer_finger2",
        "joint_greifer_finger3",
    ])

    # ── Kamera ────────────────────────────────────────────────────────────
    # RTSP URL der reCamera 2002
    cam_rtsp_url: str = "rtsp://admin:admin@192.168.188.193:554/live"
    cam_width: int = 1920
    cam_height: int = 1080
    cam_fps: int = 30
    use_camera: bool = True  # auf False setzen um ohne Kamera zu testen

    # ── Timing ────────────────────────────────────────────────────────────
    connection_timeout_s: float = 10.0
    action_duration_ms: int = 100