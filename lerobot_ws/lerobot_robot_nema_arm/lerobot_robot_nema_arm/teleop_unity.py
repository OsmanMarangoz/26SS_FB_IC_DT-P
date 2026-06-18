"""
teleop_unity.py — LeRobot Teleoperator (liest die kommandierten Gelenkwinkel).

Funktioniert mit ZWEI Quellen, je nach source_topic:

  Xbox-Servo (Standard jetzt):
      Xbox → joy_to_tcp_jac_node → /servo_joint_target (JointState) → stm32
      → liest /servo_joint_target

  Unity-Ball (alt):
      Unity → MoveIt → /planned_trajectory (JointTrajectory) → stm32
      → source_type="trajectory" setzen und planned_trajectory_topic nutzen

Der Teleoperator liest passiv mit und gibt die Zielwinkel als get_action()
an LeRobot weiter. Eure Steuer-Pipeline wird NICHT berührt.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from lerobot.teleoperators import Teleoperator, TeleoperatorConfig


@TeleoperatorConfig.register_subclass("unity_teleop")
@dataclass
class UnityTeleoperatorConfig(TeleoperatorConfig):
    # source_type: "jointstate"  → liest /servo_joint_target (Xbox)
    #              "trajectory"  → liest /planned_trajectory (Unity-Ball)
    source_type: str = "jointstate"

    # Topic je nach Quelle
    servo_target_topic: str = "/servo_joint_target"      # Xbox
    planned_trajectory_topic: str = "/planned_trajectory" # Unity-Ball

    arm_joints: list = field(default_factory=lambda: [
        "joint_basis_arm1",
        "joint_arm1_arm2",
        "joint_arm2_arm3",
        "joint_arm3_greifer",
    ])

    connection_timeout_s: float = 30.0


class UnityTeleoperator(Teleoperator):
    config_class = UnityTeleoperatorConfig
    name = "unity_teleop"

    def __init__(self, config: UnityTeleoperatorConfig):
        super().__init__(config)
        self.config = config

        self._node = None
        self._executor = None
        self._ros_thread = None
        self._latest_msg = None
        self._lock = threading.Lock()
        self._received_first = False

    # ── Pflicht-Properties ────────────────────────────────────────────────

    @property
    def action_features(self) -> dict:
        return {f"{j}.pos": float for j in self.config.arm_joints}

    @property
    def feedback_features(self) -> dict:
        return {}

    @property
    def is_connected(self) -> bool:
        return self._node is not None and self._received_first

    @property
    def is_calibrated(self) -> bool:
        return True

    def calibrate(self) -> None:
        pass

    def configure(self) -> None:
        pass

    # ── Verbindung ────────────────────────────────────────────────────────

    def connect(self) -> None:
        import rclpy
        from rclpy.executors import SingleThreadedExecutor

        if not rclpy.ok():
            rclpy.init()

        self._node = rclpy.create_node("lerobot_unity_teleop")

        if self.config.source_type == "jointstate":
            from sensor_msgs.msg import JointState
            topic = self.config.servo_target_topic
            self._node.create_subscription(JointState, topic, self._callback, 10)
        else:
            from trajectory_msgs.msg import JointTrajectory
            topic = self.config.planned_trajectory_topic
            self._node.create_subscription(JointTrajectory, topic, self._callback, 10)

        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._ros_thread = threading.Thread(
            target=self._executor.spin, daemon=True, name="unity_teleop_spin"
        )
        self._ros_thread.start()

        print(f"[Teleop] Warte auf '{topic}' (source_type={self.config.source_type})...")
        print("[Teleop] Bewege den Arm (Xbox oder Unity) um die erste Nachricht zu empfangen...")

        deadline = time.time() + self.config.connection_timeout_s
        while not self._received_first:
            if time.time() > deadline:
                raise TimeoutError(
                    f"[Teleop] Keine Nachrichten auf '{topic}' "
                    f"nach {self.config.connection_timeout_s}s.\n"
                    "Läuft die Steuer-Node (Xbox/Unity)? Wurde der Arm bewegt?"
                )
            time.sleep(0.05)

        print("[Teleop] Verbunden. Kommandos werden empfangen.")

    def disconnect(self) -> None:
        if self._executor:
            self._executor.shutdown(timeout_sec=2.0)
            self._executor = None
        if self._node:
            self._node.destroy_node()
            self._node = None
        self._received_first = False
        print("[Teleop] Getrennt.")

    # ── ROS2 Callback ─────────────────────────────────────────────────────

    def _callback(self, msg) -> None:
        with self._lock:
            self._latest_msg = msg
            self._received_first = True

    # ── Kern-Methode ──────────────────────────────────────────────────────

    def get_action(self) -> dict[str, Any]:
        with self._lock:
            msg = self._latest_msg

        if msg is None:
            return {f"{j}.pos": 0.0 for j in self.config.arm_joints}

        if self.config.source_type == "jointstate":
            # JointState: .name + .position
            names = list(msg.name)
            positions = msg.position
        else:
            # JointTrajectory: letzter Waypoint
            if not msg.points:
                return {f"{j}.pos": 0.0 for j in self.config.arm_joints}
            names = list(msg.joint_names)
            positions = msg.points[-1].positions

        action = {}
        for joint_name in self.config.arm_joints:
            if joint_name in names:
                idx = names.index(joint_name)
                action[f"{joint_name}.pos"] = float(positions[idx])
            else:
                action[f"{joint_name}.pos"] = 0.0

        return action

    def send_feedback(self, observation: dict) -> None:
        pass