from dataclasses import dataclass, field
from lerobot.robots import RobotConfig


@RobotConfig.register_subclass("nema_arm")
@dataclass
class NemaArmConfig(RobotConfig):
    """
    Configuration für den 4-DOF NEMA Stepper Arm.

    Modes:
        twin  — Unity Digital Twin: Gelenke über /joint_states,
                Kamerabilder über ROS2 sensor_msgs/Image (via rosbridge).
                Kein physischer Arm/Kameras nötig.
        real  — Physischer Arm: Gelenke über /joint_states (STM32),
                Kamerabilder über USB/RTSP (ReCamera).
                Kein Unity/rosbridge nötig.

    Topics (aus README Section 3.2 — NICHT ändern):
        /joint_states        ← stm32_serial_node oder Unity publiziert hier
        /planned_trajectory  ← unity_moveit_bridge publisht hier
        /stm32_cmd           ← unity_moveit_bridge publisht hier
    """

    # ── Mode ─────────────────────────────────────────────────────────────
    # "twin" = Unity ROS cameras (ROS2Camera)
    # "real" = physical cameras  (ReCamera)
    mode: str = "twin"

    # ── ROS2 Topics ───────────────────────────────────────────────────────
    joint_states_topic: str = "/joint_states"
    planned_trajectory_topic: str = "/planned_trajectory"
    stm32_cmd_topic: str = "/stm32_cmd"
    servo_target_topic: str = "/servo_joint_target"

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

    # ── Twin-Mode Kameras (Unity → rosbridge → ROS2 sensor_msgs/Image) ───
    # name → ROS2 Image-Topic. Jeder Eintrag wird automatisch zu
    # observation_features[name] und als Video-Stream gespeichert.
    twin_cameras: dict = field(default_factory=lambda: {
        "cam_top":  "/unity/camera_top/image_raw",
        "cam_side": "/unity/camera_side/image_raw",
    })

    # ── Real-Mode Kameras (physische USB/RTSP Kameras via ReCamera) ───────
    # name → ReCameraConfig-Kwargs. Jeder Eintrag wird als ReCamera
    # instanziiert. Beliebig erweiterbar (z.B. cam_side hinzufügen).
    real_cameras: dict = field(default_factory=lambda: {
        "cam_top": {"camera_type": "auto"},
    })

    # ── Backward-compat: altes 'cameras' dict ────────────────────────────
    # Wird jetzt dynamisch aus mode bestimmt. Dieser Default ist für
    # twin-mode gesetzt, damit bestehender Code ohne --mode weiterhin
    # funktioniert.
    cameras: dict = field(default_factory=lambda: {
        "cam_top":  "/unity/camera_top/image_raw",
        "cam_side": "/unity/camera_side/image_raw",
    })

    cam_width: int = 640
    cam_height: int = 480
    cam_fps: int = 30
    use_camera: bool = True  # auf False setzen um ohne Kamera zu testen

    # ── Timing ────────────────────────────────────────────────────────────
    connection_timeout_s: float = 30.0
    action_duration_ms: int = 100

    def __post_init__(self):
        """Update cameras dict based on selected mode."""
        if self.mode == "twin":
            self.cameras = dict(self.twin_cameras)
        elif self.mode == "real":
            self.cameras = dict(self.real_cameras)
        else:
            raise ValueError(
                f"[NemaArmConfig] Ungültiger mode='{self.mode}'. "
                f"Erlaubt: 'twin', 'real'."
            )