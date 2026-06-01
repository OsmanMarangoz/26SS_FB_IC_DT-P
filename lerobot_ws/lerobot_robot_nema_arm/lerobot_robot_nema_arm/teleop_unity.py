"""
teleop_unity.py — LeRobot Teleoperator für Unity-Teleoperation.

Eure Pipeline bleibt KOMPLETT UNVERÄNDERT:
    Unity → /robot_cmd → unity_moveit_bridge → MoveIt → /planned_trajectory
                                                              ↓
                                                   stm32_serial_node → STM32 → Motoren

Diese Klasse macht NUR EINES:
    Sie liest /planned_trajectory und gibt LeRobot die kommandierten
    Gelenkwinkel als "action" — damit der Datensatz weiß was Unity wollte.

    LeRobot speichert pro Frame:
        observation = NemaArm.get_observation()   ← echte STM32 Position
        action      = UnityTeleoperator.get_action() ← was Unity kommandiert hat
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from lerobot.teleoperators import Teleoperator, TeleoperatorConfig


@TeleoperatorConfig.register_subclass("unity_teleop")
@dataclass
class UnityTeleoperatorConfig(TeleoperatorConfig):
    # /planned_trajectory — Output von MoveIt, Input für stm32_serial_node
    # Letzter Waypoint = Zielposition die Unity kommandiert hat
    planned_trajectory_topic: str = "/planned_trajectory"

    # Muss mit NemaArmConfig.arm_joints übereinstimmen
    arm_joints: list = field(default_factory=lambda: [
        "joint_basis_arm1",
        "joint_arm1_arm2",
        "joint_arm2_arm3",
        "joint_arm3_greifer",
    ])

    connection_timeout_s: float = 30.0


class UnityTeleoperator(Teleoperator):
    """
    Liest den letzten Waypoint aus /planned_trajectory (MoveIt Output)
    und gibt ihn als get_action() an LeRobot weiter.

    Eure bestehende Pipeline wird nicht berührt — diese Klasse
    subscribed nur passiv und schreibt nichts.
    """

    config_class = UnityTeleoperatorConfig
    name = "unity_teleop"

    def __init__(self, config: UnityTeleoperatorConfig):
        super().__init__(config)
        self.config = config

        self._node = None
        self._executor = None
        self._ros_thread = None
        self._latest_traj = None
        self._traj_lock = threading.Lock()
        self._received_first = False

    # ── Pflicht-Properties ────────────────────────────────────────────────

    @property
    def action_features(self) -> dict:
        """Was get_action() zurückgibt — selbe Struktur wie NemaArm.action_features."""
        return {f"{j}.pos": float for j in self.config.arm_joints}

    @property
    def feedback_features(self) -> dict:
        """Kein Feedback nötig — Unity hat seinen eigenen Digital Twin."""
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
        """Startet ROS2 Subscriber auf /planned_trajectory."""
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from trajectory_msgs.msg import JointTrajectory

        if not rclpy.ok():
            rclpy.init()

        self._node = rclpy.create_node("lerobot_unity_teleop")

        self._node.create_subscription(
            JointTrajectory,
            self.config.planned_trajectory_topic,
            self._callback,
            10,
        )

        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._ros_thread = threading.Thread(
            target=self._executor.spin, daemon=True, name="unity_teleop_spin"
        )
        self._ros_thread.start()

        print(f"[UnityTeleop] Warte auf '{self.config.planned_trajectory_topic}'...")
        print("[UnityTeleop] Bewege den Ball in Unity um die erste Trajektorie zu empfangen...")

        deadline = time.time() + self.config.connection_timeout_s
        while not self._received_first:
            if time.time() > deadline:
                raise TimeoutError(
                    f"[UnityTeleop] Keine Nachrichten auf "
                    f"'{self.config.planned_trajectory_topic}' "
                    f"nach {self.config.connection_timeout_s}s.\n"
                    "Läuft unity_simulation.launch.py? "
                    "Wurde der Ball in Unity bewegt?"
                )
            time.sleep(0.05)

        print("[UnityTeleop] Verbunden. Unity-Trajektorien werden empfangen.")

    def disconnect(self) -> None:
        if self._executor:
            self._executor.shutdown(timeout_sec=2.0)
            self._executor = None
        if self._node:
            self._node.destroy_node()
            self._node = None
        self._received_first = False
        print("[UnityTeleop] Getrennt.")

    # ── ROS2 Callback ─────────────────────────────────────────────────────

    def _callback(self, msg) -> None:
        """Wird aufgerufen wenn MoveIt eine neue Trajektorie plant."""
        with self._traj_lock:
            self._latest_traj = msg
            self._received_first = True

    # ── Kern-Methode ──────────────────────────────────────────────────────

    def get_action(self) -> dict[str, Any]:
        """
        Gibt den Zielpunkt der letzten MoveIt-Trajektorie zurück.

        /planned_trajectory enthält mehrere Waypoints:
            [start, ..., ..., ZIEL]  ← letzter Punkt = was Unity will

        LeRobot speichert das als "action" im Datensatz:
            dataset[frame] = {
                "observation": robot.get_observation(),  ← IST-Position
                "action":      teleop.get_action(),      ← SOLL-Position
            }
        """
        with self._traj_lock:
            if self._latest_traj is None or not self._latest_traj.points:
                # Noch keine Trajektorie — Nullaktion zurückgeben
                return {f"{j}.pos": 0.0 for j in self.config.arm_joints}

            traj = self._latest_traj

        # Letzter Waypoint = Zielposition von Unity
        last_point = traj.points[-1]
        joint_names = list(traj.joint_names)

        action = {}
        for joint_name in self.config.arm_joints:
            if joint_name in joint_names:
                idx = joint_names.index(joint_name)
                action[f"{joint_name}.pos"] = float(last_point.positions[idx])
            else:
                action[f"{joint_name}.pos"] = 0.0

        return action

    def send_feedback(self, observation: dict) -> None:
        """Kein Feedback nötig — Unity hat seinen eigenen Digital Twin."""
        pass