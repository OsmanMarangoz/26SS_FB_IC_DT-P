#!/usr/bin/env python3
"""
joy_to_tcp_jac_node.py
Xbox Controller -> TCP-Velocity-Teleoperation (with Jacobian / Damped Least Squares)

would ike to use MoveIt Servo node but cannot be used, because we don't have a standard ros2 controller.
implemntation:
  Stick -> gewuenschte TCP-Geschwindigkeit (v)
        -> geometrische Jacobi-Matrix J aus Live-TF
        -> Gelenk-Geschwindigkeit  q_dot = J^T (J J^T + lambda^2 I)^-1 v   (DLS)
        -> integrieren zu Zielwinkeln
        -> /servo_joint_target (JointState) -> stm32_serial_node (Live-Stream)

Steuerung:
  LB (halten)     = Deadman
  Linker Stick    = TCP X/Y (dominante Achse)
  Rechter Stick Y = TCP Z
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

# Fallback-Gelenkgrenzen (rad) -- werden wenn moeglich aus URDF ueberschrieben
JOINT_LIMITS_FALLBACK = {
    'joint_basis_arm1':   (-6.17, 0.0),
    'joint_arm1_arm2':    (-2.04, 0.0),
    'joint_arm2_arm3':    (-2.42, 0.0),
    'joint_arm3_greifer': (-1.57, 1.57),
}

# ── Tuning-Parameter ───────────────────────────────────────────────
# tune these parameters if you want smoother motion. have not done extensive testing, but in general you can try changing all of them.
UPDATE_RATE_HZ = 100.0     # Steuerfrequenz (Hz) -- ruhig hoeher, da kein IK-Call
LINEAR_SPEED   = 0.15     # m/s TCP-Geschwindigkeit bei Stickausschlag
DEADZONE       = 0.10     # Stick-Totzone
DLS_LAMBDA     = 0.05     # Daempfung (groesser = stabiler nahe Singularitaet,
MAX_JOINT_STEP = 0.25     # rad: max Gelenkbewegung pro Tick (Sicherheits-Clamp)


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


class JoyToTcpJac(Node):
    def __init__(self):
        super().__init__('joy_to_tcp_jac')

        self.axes = []
        self.buttons = []
        self.prev_buttons = []
        self.latest_joint_state = None

        self.q_target = None        # interner Zielzustand (rad), wird integriert
        self.initialized = False

        # URDF-abgeleitete Kinematik-Infos pro Gelenk
        self.joint_axis = {}        # name -> np.array(3) lokale Achse
        self.joint_child = {}       # name -> child link frame
        self.joint_limits = dict(JOINT_LIMITS_FALLBACK)
        self.urdf_ready = False

        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        self.target_pub = self.create_publisher(
            JointState, '/servo_joint_target', 10)
        self.stm32_pub = self.create_publisher(String, '/stm32_cmd', 10)

        self.create_subscription(Joy, '/joy', self.joy_cb, 10)
        self.create_subscription(JointState, '/joint_states', self.js_cb, 10)

        # /robot_description ist latched (transient_local)
        qos = QoSProfile(depth=1,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL,
                         history=HistoryPolicy.KEEP_LAST)
        self.create_subscription(String, '/robot_description',
                                 self.urdf_cb, qos)

        self.timer = self.create_timer(1.0 / UPDATE_RATE_HZ, self.control_loop)

        self.get_logger().info(
            'joy_to_tcp_jac bereit (Jacobian/DLS).\n'
            '  LB halten     = Bewegung aktiv (Deadman)\n'
            '  Linker Stick  = TCP X/Y\n'
            '  Rechter Stick = TCP Z\n'
            '  A / B         = Greifer auf / zu\n'
            '  Start / Back  = home / reset\n'
            '  (warte auf /robot_description ...)')

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
            self.get_logger().info('URDF geparst -- Kinematik bereit.')
        except Exception as e:
            self.get_logger().error(f'URDF-Parsing fehlgeschlagen: {e}')

    def _parse_urdf(self, urdf_xml):
        root = ET.fromstring(urdf_xml)
        for joint in root.findall('joint'):
            name = joint.get('name')
            if name not in ARM_JOINTS:
                continue
            # Achse (default 1 0 0)
            axis_el = joint.find('axis')
            if axis_el is not None and axis_el.get('xyz'):
                ax = [float(v) for v in axis_el.get('xyz').split()]
            else:
                ax = [1.0, 0.0, 0.0]
            self.joint_axis[name] = np.array(ax, dtype=float)
            # Child-Link Frame
            child_el = joint.find('child')
            if child_el is not None:
                self.joint_child[name] = child_el.get('link')
            # Limits
            lim = joint.find('limit')
            if lim is not None and lim.get('lower') and lim.get('upper'):
                self.joint_limits[name] = (float(lim.get('lower')),
                                           float(lim.get('upper')))

    # ── Hilfen ──────────────────────────────────────────────────────
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

    @staticmethod
    def _sign(v):
        return 1.0 if v > 0 else (-1.0 if v < 0 else 0.0)

    def _tf_pose(self, frame):
        """world->frame: (R 3x3, p 3) oder None."""
        try:
            tf = self.tf_buffer.lookup_transform(
                BASE_FRAME, frame, rclpy.time.Time())
        except Exception:
            return None
        t = tf.transform.translation
        r = tf.transform.rotation
        R = rot_from_quat(r.x, r.y, r.z, r.w)
        p = np.array([t.x, t.y, t.z])
        return R, p

    def _build_jacobian(self):
        """Geometrische Positions-Jacobi (3 x n) aus Live-TF."""
        tcp = self._tf_pose(TCP_LINK)
        if tcp is None:
            return None
        _, p_tcp = tcp

        cols = []
        for jname in ARM_JOINTS:
            child = self.joint_child.get(jname)
            pose = self._tf_pose(child) if child else None
            if pose is None:
                return None
            R, p_joint = pose
            axis_world = R @ self.joint_axis[jname]
            # Lineare Jacobi-Spalte fuer Drehgelenk: z x (p_tcp - p_joint)
            col = np.cross(axis_world, (p_tcp - p_joint))
            cols.append(col)
        return np.array(cols).T   # 3 x n

    # ── Hauptschleife ───────────────────────────────────────────────
    def control_loop(self):
        if not self.buttons or self.latest_joint_state is None:
            return
        if not self.urdf_ready:
            return

        # Greifer + System (Flanken)
        if self._pressed(BTN_A):
            self._send_cmd('grip_open')
        if self._pressed(BTN_B):
            self._send_cmd('grip_close')
        if self._pressed(BTN_START):
            self._send_cmd('home')
        if self._pressed(BTN_BACK):
            self._send_cmd('reset')
        self.prev_buttons = list(self.buttons)

        # Internen Zielzustand initialisieren aus aktuellen Gelenkwinkeln
        if not self.initialized:
            cur = dict(zip(self.latest_joint_state.name,
                           self.latest_joint_state.position))
            if all(j in cur for j in ARM_JOINTS):
                self.q_target = np.array([cur[j] for j in ARM_JOINTS])
                self.initialized = True
            return

        # Deadman
        if len(self.buttons) <= BTN_LB or self.buttons[BTN_LB] != 1:
            return

        # Stick -> gewuenschte TCP-Geschwindigkeit (world frame)
        ly = self._raw_axis(AXIS_LEFTY)
        lx = self._raw_axis(AXIS_LEFTX)
        if abs(ly) >= abs(lx):
            vx, vy = self._sign(ly), 0.0
        else:
            vx, vy = 0.0, self._sign(lx)
        vz = self._sign(self._raw_axis(AXIS_RIGHTY))

        if vx == 0.0 and vy == 0.0 and vz == 0.0:
            return

        v = np.array([vx, vy, vz]) * LINEAR_SPEED   # m/s

        J = self._build_jacobian()
        if J is None:
            return

        # Damped Least Squares: q_dot = J^T (J J^T + lambda^2 I)^-1 v
        n = J.shape[1]
        JJt = J @ J.T
        damp = (DLS_LAMBDA ** 2) * np.eye(3)
        try:
            q_dot = J.T @ np.linalg.solve(JJt + damp, v)
        except np.linalg.LinAlgError:
            return

        dt = 1.0 / UPDATE_RATE_HZ
        dq = q_dot * dt

        # Sicherheits-Clamp pro Tick
        np.clip(dq, -MAX_JOINT_STEP, MAX_JOINT_STEP, out=dq)

        q_new = self.q_target + dq

        # Gelenkgrenzen einhalten
        for i, jname in enumerate(ARM_JOINTS):
            lo, hi = self.joint_limits[jname]
            q_new[i] = max(lo, min(hi, q_new[i]))

        self.q_target = q_new

        out = JointState()
        out.header.stamp = self.get_clock().now().to_msg()
        out.name = list(ARM_JOINTS)
        out.position = [float(q) for q in q_new]
        self.target_pub.publish(out)

    def _send_cmd(self, text):
        msg = String()
        msg.data = text
        self.stm32_pub.publish(msg)
        self.get_logger().info(f'/stm32_cmd -> {text}')


def main(args=None):
    rclpy.init(args=args)
    node = JoyToTcpJac()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()