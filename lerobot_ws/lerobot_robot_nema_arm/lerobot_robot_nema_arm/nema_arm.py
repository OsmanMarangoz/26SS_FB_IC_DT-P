"""
nema_arm.py — LeRobot Robot Klasse für den 4-DOF NEMA Stepper Arm.

Bestehende Pipeline bleibt KOMPLETT UNVERÄNDERT:
    Unity → /robot_cmd → unity_moveit_bridge → MoveIt
                                                  ↓ /planned_trajectory
                                             stm32_serial_node → STM32 → Motoren
                                                  ↓
                                             /joint_states (200 Hz, 7 joints)
                                                  ↓
                                        NemaArm.get_observation() ← LeRobot liest hier
"""

import threading
import time
from typing import Any

from lerobot.robots import Robot

from .config_nema_arm import NemaArmConfig
from .ros2_camera import ROS2Camera, ROS2CameraConfig


class NemaArm(Robot):
    config_class = NemaArmConfig
    name = "nema_arm"

    def __init__(self, config: NemaArmConfig):
        super().__init__(config)
        self.config = config

        # ROS2 internals
        self._node = None
        self._executor = None
        self._ros_thread = None
        self._joint_sub = None
        self._traj_pub = None
        self._cmd_pub = None

        self._latest_joint_state = None
        self._js_lock = threading.Lock()
        self._received_first_js = False

        # Kameras initialisieren (nur wenn use_camera=True)
        # Jede Kamera ist ein Unity-Render, das via rosbridge als
        # sensor_msgs/Image auf einem ROS2-Topic ankommt. Beliebig viele
        # möglich — eine ROS2Camera pro Eintrag in config.cameras.
        if config.use_camera:
            self.cameras = {
                name: ROS2Camera(ROS2CameraConfig(
                    image_topic=topic,
                    width=config.cam_width,
                    height=config.cam_height,
                    fps=config.cam_fps,
                ))
                for name, topic in config.cameras.items()
            }
        else:
            self.cameras = {}

    # ════════════════════════════════════════════════════════════════════
    #  Feature Deklarationen
    # ════════════════════════════════════════════════════════════════════

    @property
    def observation_features(self) -> dict:
        features = {}
        for j in self.config.arm_joints:
            features[f"{j}.pos"] = float
        for j in self.config.finger_joints:
            features[f"{j}.pos"] = float
        if self.config.use_camera:
            for cam_name in self.cameras:
                features[cam_name] = (self.config.cam_height, self.config.cam_width, 3)
        return features

    @property
    def action_features(self) -> dict:
        return {f"{j}.pos": float for j in self.config.arm_joints}

    # ════════════════════════════════════════════════════════════════════
    #  Verbindung
    # ════════════════════════════════════════════════════════════════════

    @property
    def is_connected(self) -> bool:
        return self._node is not None and self._received_first_js

    def connect(self, calibrate: bool = True) -> None:
        """
        Startet ROS2 Subscriber auf /joint_states.
        Verbindet Kamera falls use_camera=True.
        calibrate wird ignoriert — STM32 Homing ist die Kalibrierung.
        """
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from sensor_msgs.msg import JointState
        from std_msgs.msg import String
        from trajectory_msgs.msg import JointTrajectory

        if not rclpy.ok():
            rclpy.init()

        self._node = rclpy.create_node("lerobot_nema_arm")

        self._joint_sub = self._node.create_subscription(
            JointState,
            self.config.joint_states_topic,
            self._joint_state_callback,
            10,
        )

        self._traj_pub = self._node.create_publisher(
            JointTrajectory,
            self.config.planned_trajectory_topic,
            10,
        )

        self._cmd_pub = self._node.create_publisher(
            String,
            self.config.stm32_cmd_topic,
            10,
        )

        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._ros_thread = threading.Thread(
            target=self._executor.spin, daemon=True, name="lerobot_ros_spin"
        )
        self._ros_thread.start()

        print(f"[NemaArm] Warte auf '{self.config.joint_states_topic}'...")
        deadline = time.time() + self.config.connection_timeout_s
        while not self._received_first_js:
            if time.time() > deadline:
                raise TimeoutError(
                    f"[NemaArm] Keine Nachrichten auf '{self.config.joint_states_topic}' "
                    f"nach {self.config.connection_timeout_s}s.\n"
                    "Läuft unity_simulation.launch.py?"
                )
            time.sleep(0.05)

        print(f"[NemaArm] Verbunden. "
              f"{len(self.config.arm_joints)} Arm-Joints + "
              f"{len(self.config.finger_joints)} Finger-Joints.")

        # Kamera verbinden
        for cam_name, cam in self.cameras.items():
            cam.connect()
            print(f"[NemaArm] Kamera '{cam_name}' verbunden.")

    def disconnect(self) -> None:
        for cam_name, cam in self.cameras.items():
            cam.disconnect()

        if self._executor:
            self._executor.shutdown(timeout_sec=2.0)
            self._executor = None
        if self._node:
            self._node.destroy_node()
            self._node = None

        self._received_first_js = False
        self._latest_joint_state = None
        print("[NemaArm] Getrennt.")

    # ════════════════════════════════════════════════════════════════════
    #  Kalibrierung & Konfiguration
    # ════════════════════════════════════════════════════════════════════

    @property
    def is_calibrated(self) -> bool:
        return True

    def calibrate(self) -> None:
        pass

    def configure(self) -> None:
        pass

    # ════════════════════════════════════════════════════════════════════
    #  ROS2 Callback
    # ════════════════════════════════════════════════════════════════════

    def _joint_state_callback(self, msg) -> None:
        with self._js_lock:
            self._latest_joint_state = msg
            self._received_first_js = True

    # ════════════════════════════════════════════════════════════════════
    #  Core I/O
    # ════════════════════════════════════════════════════════════════════

    def get_observation(self) -> dict[str, Any]:
        """
        Liest aktuelle Gelenkpositionen aus /joint_states.
        7 Joints: 4 Arm + 3 Finger.
        Optional: Kamera-Frame von reCamera.
        """
        if not self.is_connected:
            raise ConnectionError("[NemaArm] Nicht verbunden. connect() aufrufen.")

        with self._js_lock:
            js = self._latest_joint_state

        obs = {}
        for joint_name in self.config.arm_joints + self.config.finger_joints:
            if joint_name in js.name:
                idx = list(js.name).index(joint_name)
                obs[f"{joint_name}.pos"] = float(js.position[idx])
            else:
                obs[f"{joint_name}.pos"] = 0.0

        for cam_name, cam in self.cameras.items():
            obs[cam_name] = cam.async_read()

        return obs

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        """
        Sendet Ziel-Gelenkpositionen an stm32_serial_node via /planned_trajectory.
        """
        if not self.is_connected:
            raise ConnectionError("[NemaArm] Nicht verbunden.")

        from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
        from builtin_interfaces.msg import Duration

        traj = JointTrajectory()
        traj.joint_names = list(self.config.arm_joints)

        point = JointTrajectoryPoint()
        point.positions = [
            float(action.get(f"{j}.pos", 0.0)) for j in self.config.arm_joints
        ]
        duration_ns = self.config.action_duration_ms * 1_000_000
        point.time_from_start = Duration(sec=0, nanosec=duration_ns)
        traj.points.append(point)

        self._traj_pub.publish(traj)
        return action

    def send_command(self, cmd: str) -> None:
        """
        Spezial-Kommandos an stm32_serial_node:
            "reset", "home", "grip_open", "grip_close", "estop"
        """
        if not self.is_connected:
            raise ConnectionError("[NemaArm] Nicht verbunden.")

        from std_msgs.msg import String
        msg = String()
        msg.data = cmd.strip().lower()
        self._cmd_pub.publish(msg)
        print(f"[NemaArm] Kommando gesendet: '{cmd}'")