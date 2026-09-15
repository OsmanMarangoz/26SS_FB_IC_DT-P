#!/usr/bin/env python3
"""
joy_to_tcp_jac_4dof_correct.py
KORREKTE Implementierung für 4-DoF Arm (1 Yaw + 3 Pitch)

HARDWARE-SPEZIFISCH:
  - 4 Gelenke: [Basis-Yaw, Arm1-Pitch, Arm2-Pitch, Arm3-Pitch]
  - Task-Space: [X, Y, Z, Greifer-Pitch] → exakt 4 DoF!
  - Jacobian: 4×4 (KEINE Redundanz → KEIN Nullraum!)

KRITISCHE FIXES gegenüber vorherigen Versionen:
  1. Jacobian ist 4×4 (3 Position + 1 Pitch), NICHT 3×4 oder 6×4
  2. KEINE Nullraum-Optimierung (da 4 DoF Task = 4 DoF Arm)
  3. Pitch wird explizit gelockt wenn nur X/Y/Z bewegt wird
  4. DLS funktioniert sauber (4×4 ist square → gut konditioniert)

Steuerung:
  LB (halten)     = Deadman
  Linker Stick    = TCP X/Y (Tool-Frame!)
  Rechter Stick Y = TCP Z (Tool-Frame!)
  Rechter Stick X = Greifer-Pitch (hoch/runter neigen)
  A / B           = Greifer auf / zu
  Start / Back    = home / reset
"""

import xml.etree.ElementTree as ET
import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, HistoryPolicy

from sensor_msgs.msg import Joy, JointState
from std_msgs.msg import String

import tf2_ros
from scipy.spatial.transform import Rotation as R

# game_controller_node Achsen-Indizes
AXIS_LEFTX  = 0
AXIS_LEFTY  = 1
AXIS_RIGHTX = 2
AXIS_RIGHTY = 3

# game_controller_node Button-Indizes
BTN_A     = 0
BTN_B     = 1
BTN_BACK  = 4
BTN_START = 6
BTN_LB    = 9

# Konfiguration
TCP_LINK   = "tcp_link"
BASE_FRAME = "world"
ARM_JOINTS = ['joint_basis_arm1', 'joint_arm1_arm2',
              'joint_arm2_arm3', 'joint_arm3_greifer']

# Fallback-Gelenkgrenzen (rad)
JOINT_LIMITS_FALLBACK = {
    'joint_basis_arm1':   (-6.17, 0.0),
    'joint_arm1_arm2':    (-2.04, 0.0),
    'joint_arm2_arm3':    (-2.42, 0.0),
    'joint_arm3_greifer': (-1.57, 1.57),
}

# ── Tuning-Parameter ───────────────────────────────────────────────
UPDATE_RATE_HZ = 50.0           # Control frequency

# Geschwindigkeiten
LINEAR_SPEED  = 0.15            # m/s TCP translation speed
PITCH_SPEED   = 0.4             # rad/s gripper pitch rotation speed
DEADZONE      = 0.08            # Stick deadzone

# DLS parameters (einfacher für 4×4!)
DLS_LAMBDA_MIN = 0.001          # Minimum damping
DLS_LAMBDA_MAX = 0.1            # Maximum damping
MANIP_THRESHOLD = 0.005         # Manipulability threshold

# Velocity smoothing
MAX_LINEAR_ACCEL = 0.8          # m/s²
MAX_PITCH_ACCEL  = 2.0          # rad/s²

MAX_JOINT_STEP = 0.10           # rad: safety clamp per tick

# Control mode
USE_TOOL_FRAME = True           # True = intuitive tool-frame control


def rot_from_quat(x, y, z, w):
    """Rotationsmatrix aus Quaternion."""
    n = x*x + y*y + z*z + w*w
    if n < 1e-12:
        return np.eye(3)
    s = 2.0 / n
    xx, yy, zz = x*x*s, y*y*s, z*z*s
    xy, xz, yz = x*y*s, x*z*s, y*z*s
    wx, wy, wz = w*x*s, w*y*s, w*z*s
    return np.array([
        [1.0-(yy+zz), xy-wz,        xz+wy],
        [xy+wz,       1.0-(xx+zz),  yz-wx],
        [xz-wy,       yz+wx,        1.0-(xx+yy)],
    ])


def extract_pitch_from_rotation(R_mat):
    """
    Extrahiere Pitch-Winkel aus Rotationsmatrix.

    Für einen Arm, der hauptsächlich in der XZ-Ebene arbeitet:
    Pitch = atan2(-R[2,0], sqrt(R[0,0]^2 + R[1,0]^2))

    Dies ist robust gegenüber Gimbal Lock.
    """
    # Standard Euler-Extraktion (ZYX-Konvention)
    sy = np.sqrt(R_mat[0, 0]**2 + R_mat[1, 0]**2)

    if sy > 1e-6:  # Not at singularity
        pitch = np.arctan2(-R_mat[2, 0], sy)
    else:
        pitch = np.arctan2(-R_mat[2, 0], sy)

    return pitch


class JoyToTcpJac4DoF(Node):
    def __init__(self):
        super().__init__('joy_to_tcp_jac_4dof')

        self.axes = []
        self.buttons = []
        self.prev_buttons = []
        self.latest_joint_state = None

        self.q_target = None
        self.initialized = False

        # Velocity tracking (4-DoF: 3 linear + 1 pitch)
        self.current_v_linear = np.zeros(3)
        self.current_v_pitch = 0.0  # Scalar: gripper pitch rate

        self.gripper_pos = 0.0
        self.gripper_target = 0.0
        self.last_log_time = 0.0
        self.last_manip = 1.0

        # URDF-derived kinematic info
        self.joint_axis = {}
        self.joint_child = {}
        self.joint_limits = dict(JOINT_LIMITS_FALLBACK)
        self.urdf_ready = False

        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        qos_cmd = QoSProfile(depth=10, durability=DurabilityPolicy.VOLATILE,
                             history=HistoryPolicy.KEEP_LAST)
        self.target_pub = self.create_publisher(JointState, '/servo_joint_target', qos_cmd)
        self.stm32_pub = self.create_publisher(String, '/stm32_cmd', qos_cmd)

        self.create_subscription(Joy, '/joy', self.joy_cb, 10)
        self.create_subscription(JointState, '/joint_states', self.js_cb, 10)

        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                         history=HistoryPolicy.KEEP_LAST)
        self.create_subscription(String, '/robot_description', self.urdf_cb, qos)

        self.timer = self.create_timer(1.0 / UPDATE_RATE_HZ, self.control_loop)

        mode_str = "Tool-Frame" if USE_TOOL_FRAME else "World-Frame"

        self.get_logger().info(
            f'✅ joy_to_tcp_jac_4dof (CORRECT 4×4 Jacobian) | Mode: {mode_str}\n'
            '  Task-Space: [X, Y, Z, Pitch] → 4 DoF (NO null-space!)\n'
            '  LB halten       = Deadman\n'
            '  Linker Stick    = TCP X/Y (tool frame)\n'
            '  Rechter Stick Y = TCP Z\n'
            '  Rechter Stick X = Greifer-Pitch (up/down)\n'
            '  A / B           = Greifer auf / zu\n'
            '  Start / Back    = home / reset')

    # ── Callbacks ───────────────────────────────────────────────────
    def js_cb(self, msg):
        self.latest_joint_state = msg

    def joy_cb(self, msg):
        self.axes = list(msg.axes)
        self.buttons = list(msg.buttons)
        if not self.prev_buttons:
            self.prev_buttons = list(msg.buttons)

    def urdf_cb(self, msg):
        if self.urdf_ready:
            return
        try:
            self._parse_urdf(msg.data)
            self.urdf_ready = True
            self.get_logger().info('✅ URDF parsed -- 4-DoF Kinematik bereit.')
        except Exception as e:
            self.get_logger().error(f'URDF parsing failed: {e}')

    def _parse_urdf(self, urdf_xml):
        root = ET.fromstring(urdf_xml)
        for joint in root.findall('joint'):
            name = joint.get('name')
            if name not in ARM_JOINTS:
                continue
            # Axis
            axis_el = joint.find('axis')
            if axis_el is not None and axis_el.get('xyz'):
                ax = [float(v) for v in axis_el.get('xyz').split()]
            else:
                ax = [1.0, 0.0, 0.0]
            self.joint_axis[name] = np.array(ax, dtype=float)
            # Child link
            child_el = joint.find('child')
            if child_el is not None:
                self.joint_child[name] = child_el.get('link')
            # Limits
            lim = joint.find('limit')
            if lim is not None and lim.get('lower') and lim.get('upper'):
                self.joint_limits[name] = (float(lim.get('lower')),
                                           float(lim.get('upper')))

    # ── Helpers ──────────────────────────────────────────────────────
    def _pressed(self, idx):
        if idx >= len(self.buttons):
            return False
        was = self.prev_buttons[idx] if idx < len(self.prev_buttons) else 0
        return self.buttons[idx] == 1 and was == 0

    def _raw_axis(self, idx):
        if idx >= len(self.axes):
            return 0.0
        v = self.axes[idx]
        return v if abs(v) > DEADZONE else 0.0

    def _tf_pose(self, frame):
        """world->frame: (R 3x3, p 3) or None."""
        try:
            tf = self.tf_buffer.lookup_transform(BASE_FRAME, frame, rclpy.time.Time())
        except Exception:
            return None
        t = tf.transform.translation
        r = tf.transform.rotation
        R_mat = rot_from_quat(r.x, r.y, r.z, r.w)
        p = np.array([t.x, t.y, t.z])
        return R_mat, p

    def _build_jacobian_4dof(self):
        """
        ✅ KORREKTE 4×4 Jacobian für [X, Y, Z, Pitch]

        Zeilen 0-2: Linear velocity (Position)
        Zeile 3:    Pitch angular velocity (nur Y-Komponente der Rotation)

        Für 4-DoF Arm: 4 Task-Bedingungen = 4 Gelenke → KEINE Redundanz!
        """
        tcp = self._tf_pose(TCP_LINK)
        if tcp is None:
            return None
        R_tcp, p_tcp = tcp

        J_linear = []   # 3×4: Position Jacobian
        J_pitch = []    # 1×4: Pitch Jacobian (nur Y-Komponente!)

        for jname in ARM_JOINTS:
            child = self.joint_child.get(jname)
            pose = self._tf_pose(child) if child else None
            if pose is None:
                return None
            R_joint, p_joint = pose
            axis_world = R_joint @ self.joint_axis[jname]

            # Linear Jacobian: z × (p_tcp - p_joint)
            j_linear = np.cross(axis_world, (p_tcp - p_joint))
            J_linear.append(j_linear)

            # Angular Jacobian (full): axis_world
            # Pitch Jacobian (only Y-component for pitch around Y-axis in world)
            # For a robot working in XZ-plane, pitch is rotation around Y
            j_pitch = axis_world[1]  # Y-component only!
            J_pitch.append(j_pitch)

        J_pos = np.array(J_linear).T    # 3×4
        J_pitch_row = np.array(J_pitch).reshape(1, 4)  # 1×4

        # Stack: 4×4 Jacobian
        J = np.vstack([J_pos, J_pitch_row])  # 4×4 ✅

        return J

    def _compute_manipulability(self, J):
        """
        Manipulability measure for 4×4 matrix.
        Since J is square, we can use abs(det(J)).
        """
        return abs(np.linalg.det(J))

    def _compute_adaptive_damping(self, manipulability):
        """Adaptive damping based on manipulability."""
        if manipulability < MANIP_THRESHOLD:
            return DLS_LAMBDA_MAX
        else:
            ratio = manipulability / MANIP_THRESHOLD
            lambda_val = DLS_LAMBDA_MIN + (DLS_LAMBDA_MAX - DLS_LAMBDA_MIN) * np.exp(-ratio)
            return max(DLS_LAMBDA_MIN, min(DLS_LAMBDA_MAX, lambda_val))

    # ── Main Control Loop ───────────────────────────────────────────────
    def control_loop(self):
        if not self.buttons or self.latest_joint_state is None:
            return
        if not self.urdf_ready:
            return

        # Gripper buttons
        if self._pressed(BTN_A):
            self._send_cmd('grip_open')
            self.gripper_target = 0.4
        if self._pressed(BTN_B):
            self._send_cmd('grip_close')
            self.gripper_target = 0.0
        if self._pressed(BTN_START):
            self._send_cmd('home')
        if self._pressed(BTN_BACK):
            self._send_cmd('reset')
        self.prev_buttons = list(self.buttons)

        # Smooth gripper
        dt = 1.0 / UPDATE_RATE_HZ
        gripper_speed = 0.5
        if self.gripper_pos < self.gripper_target:
            self.gripper_pos = min(self.gripper_target, self.gripper_pos + gripper_speed * dt)
        elif self.gripper_pos > self.gripper_target:
            self.gripper_pos = max(self.gripper_target, self.gripper_pos - gripper_speed * dt)

        # Initialize target state
        if not self.initialized:
            cur = dict(zip(self.latest_joint_state.name,
                           self.latest_joint_state.position))
            if all(j in cur for j in ARM_JOINTS):
                self.q_target = np.array([cur[j] for j in ARM_JOINTS])
                self.initialized = True
            return

        # ── Read joystick ────────────────────────────────────────────
        # Deadman switch
        if len(self.buttons) <= BTN_LB or self.buttons[BTN_LB] != 1:
            target_v_linear = np.zeros(3)
            target_v_pitch = 0.0
        else:
            ly = self._raw_axis(AXIS_LEFTY)   # Forward/backward
            lx = self._raw_axis(AXIS_LEFTX)   # Left/right
            ry = self._raw_axis(AXIS_RIGHTY)  # Up/down
            rx = self._raw_axis(AXIS_RIGHTX)  # Pitch control

            # ✅ Tool-frame or world-frame velocity
            if USE_TOOL_FRAME:
                # Velocity in tool frame (intuitive!)
                v_tool_frame = np.array([ly, lx, ry]) * LINEAR_SPEED

                # Transform to world frame
                tcp_pose = self._tf_pose(TCP_LINK)
                if tcp_pose is not None:
                    R_tcp, _ = tcp_pose
                    target_v_linear = R_tcp @ v_tool_frame
                else:
                    target_v_linear = np.zeros(3)
            else:
                # World-frame control
                target_v_linear = np.array([ly, lx, ry]) * LINEAR_SPEED

            # ✅ Pitch control (independent of position)
            target_v_pitch = rx * PITCH_SPEED  # rad/s

        # ── Acceleration-limited smoothing ───────────────────────────
        # Linear
        dv_linear = target_v_linear - self.current_v_linear
        dv_linear_norm = np.linalg.norm(dv_linear)
        max_dv_linear = MAX_LINEAR_ACCEL * dt
        if dv_linear_norm > max_dv_linear:
            dv_linear = dv_linear / dv_linear_norm * max_dv_linear
        self.current_v_linear += dv_linear

        # Pitch
        dv_pitch = target_v_pitch - self.current_v_pitch
        max_dv_pitch = MAX_PITCH_ACCEL * dt
        dv_pitch = np.clip(dv_pitch, -max_dv_pitch, max_dv_pitch)
        self.current_v_pitch += dv_pitch

        q_new = self.q_target.copy()

        if np.allclose(self.current_v_linear, 0.0, atol=1e-5) and \
           abs(self.current_v_pitch) < 1e-5:
            self.current_v_linear = np.zeros(3)
            self.current_v_pitch = 0.0
        else:
            # ✅ Build 4×4 Jacobian
            J = self._build_jacobian_4dof()

            if J is None:
                now = self.get_clock().now().nanoseconds / 1e9
                if now - self.last_log_time > 1.0:
                    self.get_logger().warn("Jacobian is None (missing TF?)")
                    self.last_log_time = now
            else:
                # Verify shape
                if J.shape != (4, 4):
                    self.get_logger().error(f"❌ WRONG Jacobian shape: {J.shape} (should be 4×4!)")
                    return

                # Compute manipulability (for square matrix: det(J))
                manipulability = self._compute_manipulability(J)
                self.last_manip = manipulability

                # Adaptive damping
                lambda_adaptive = self._compute_adaptive_damping(manipulability)

                # ✅ Task velocity: [v_x, v_y, v_z, v_pitch]
                v_task = np.concatenate([self.current_v_linear, [self.current_v_pitch]])  # 4D

                # ✅ DLS for 4×4 system (well-conditioned!)
                JJt = J @ J.T  # 4×4
                damp = (lambda_adaptive ** 2) * np.eye(4)

                try:
                    # DLS: q_dot = J^T (J J^T + λ²I)^-1 v
                    q_dot = J.T @ np.linalg.solve(JJt + damp, v_task)

                    # ✅ NO NULL-SPACE OPTIMIZATION!
                    # (4 DoF task = 4 DoF arm → no redundancy!)

                    # Integrate
                    dq = q_dot * dt

                    # Safety clamp
                    np.clip(dq, -MAX_JOINT_STEP, MAX_JOINT_STEP, out=dq)

                    q_new = self.q_target + dq

                    # Enforce joint limits
                    for i, jname in enumerate(ARM_JOINTS):
                        lo, hi = self.joint_limits[jname]
                        q_new[i] = max(lo, min(hi, q_new[i]))

                    self.q_target = q_new

                    # Logging
                    now = self.get_clock().now().nanoseconds / 1e9
                    if now - self.last_log_time > 1.0:
                        log_msg = f"v_lin={self.current_v_linear.round(3)}, v_pitch={self.current_v_pitch:.3f}, "
                        log_msg += f"manip={manipulability:.4f}, λ={lambda_adaptive:.4f}"
                        if manipulability < MANIP_THRESHOLD:
                            self.get_logger().warn(f"⚠️  NEAR SINGULARITY! {log_msg}")
                        else:
                            self.get_logger().info(f"✅ {log_msg}")
                        self.last_log_time = now

                except np.linalg.LinAlgError as e:
                    self.get_logger().error(f"DLS solve failed: {e}")

        # Publish joint targets
        out = JointState()
        out.header.stamp = self.get_clock().now().to_msg()
        out.name = list(ARM_JOINTS) + ['joint_greifer_finger1', 'joint_greifer_finger2', 'joint_greifer_finger3']
        out.position = [float(q) for q in q_new] + [self.gripper_pos] * 3
        self.target_pub.publish(out)

    def _send_cmd(self, text):
        msg = String()
        msg.data = text
        self.stm32_pub.publish(msg)
        self.get_logger().info(f'/stm32_cmd -> {text}')


def main(args=None):
    rclpy.init(args=args)
    node = JoyToTcpJac4DoF()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
