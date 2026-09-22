"""
teleop_unity.py — LeRobot Teleoperator.

Funktioniert mit ZWEI Quellen, je nach source_topic:

  Xbox-Servo (Standard jetzt):
      Xbox → joy_to_tcp_jac_node → /servo_joint_target (JointState) → stm32
      → liest /servo_joint_target

  Unity-Ball (alt):
      Unity → MoveIt → /planned_trajectory (JointTrajectory) → stm32
      → source_type="trajectory" setzen und planned_trajectory_topic nutzen

Der Teleoperator liest passiv mit und gibt die Zielwinkel als get_action()
an LeRobot weiter.
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

    finger_joints: list = field(default_factory=lambda: [
        "joint_greifer_finger1",
        "joint_greifer_finger2",
        "joint_greifer_finger3",
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
        all_joints = list(self.config.arm_joints) + list(self.config.finger_joints)
        return {f"{j}.pos": float for j in all_joints}

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
        if self.is_connected:
            return

        import rclpy
        from rclpy.node import Node
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

        if not rclpy.ok():
            rclpy.init(args=None)

        self._node = Node("unity_teleop_node")
        
        # Publisher ist VOLATILE, wir müssen als Subscriber auch VOLATILE sein
        qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE
        )

        if self.config.source_type == "jointstate":
            from sensor_msgs.msg import JointState
            self._node.create_subscription(
                JointState,
                self.config.servo_target_topic,
                self._callback,
                qos
            )
        else:
            from trajectory_msgs.msg import JointTrajectory
            self._node.create_subscription(
                JointTrajectory,
                self.config.planned_trajectory_topic,
                self._callback,
                qos
            )

        self._executor = rclpy.executors.SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._ros_thread = threading.Thread(target=self._executor.spin, daemon=True)
        self._ros_thread.start()

        print(f"[UnityTeleop] Warte auf '{self.config.source_type}' Nachricht...")
        start_t = time.time()
        while not self._received_first:
            time.sleep(0.1)
            if time.time() - start_t > self.config.connection_timeout_s:
                raise TimeoutError("[UnityTeleop] Timeout beim Warten auf ROS 2 Teleop-Nachricht.")
        
        print("[UnityTeleop] Verbunden.")

    def disconnect(self) -> None:
        if not self.is_connected:
            return
        import rclpy
        self._executor.shutdown()
        self._node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        self._ros_thread.join()
        self._node = None
        self._received_first = False

    # ── ROS2 Callback ─────────────────────────────────────────────────────

    def _callback(self, msg) -> None:
        with self._lock:
            self._latest_msg = msg
            self._received_first = True

    # ── Kern-Methode ──────────────────────────────────────────────────────

    def get_action(self) -> dict[str, Any]:
        with self._lock:
            msg = self._latest_msg

        all_joints = list(self.config.arm_joints) + list(self.config.finger_joints)

        if msg is None:
            return {f"{j}.pos": 0.0 for j in all_joints}

        if self.config.source_type == "jointstate":
            # JointState: .name + .position
            names = list(msg.name)
            positions = msg.position
        else:
            # JointTrajectory: letzter Waypoint
            if not msg.points:
                return {f"{j}.pos": 0.0 for j in all_joints}
            names = list(msg.joint_names)
            positions = msg.points[-1].positions

        action = {}
        for joint_name in all_joints:
            if joint_name in names:
                idx = names.index(joint_name)
                action[f"{joint_name}.pos"] = float(positions[idx])
            else:
                action[f"{joint_name}.pos"] = 0.0

        return action

    def send_feedback(self, observation: dict) -> None:
        pass