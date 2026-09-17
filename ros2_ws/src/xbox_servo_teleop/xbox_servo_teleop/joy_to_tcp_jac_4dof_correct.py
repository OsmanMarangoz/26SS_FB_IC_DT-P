#!/usr/bin/env python3
"""
joy_to_tcp_jac_4dof_correct.py -> REFACTORED TO: joy_to_joint_4dof

Intuitive Joint-Space Steuerung für 4-DoF Arm (Keine störenden Ausgleichsbewegungen mehr!)

Steuerung (Gelenk-basiert):
  LB (halten)     = Deadman
  RB (halten)     = Precision Mode (30% speed)
  Linker Stick L/R= Basis drehen (Yaw, invertiert)
  Linker Stick U/D= Arm 1 hoch/runter (Pitch 1)
  Rechter Stick U/D = Arm 2 hoch/runter (Pitch 2)
  Rechter Stick L/R = Greifer neigen (Pitch 3)
  A / B           = Greifer auf / zu
  Start / Back    = Home / Deadman Toggle
"""

import xml.etree.ElementTree as ET
import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, HistoryPolicy

from sensor_msgs.msg import Joy, JointState
from std_msgs.msg import String

# Achsen-Indizes
# HINWEIS: Wenn Right Stick L/R den Greifer neigt anstatt U/D, ändere AXIS_RIGHTY auf 4! (Xbox Standard)
AXIS_LEFTX  = 0
AXIS_LEFTY  = 1
AXIS_RIGHTX = 2
AXIS_RIGHTY = 3  
AXIS_DPAD_X = 6  # Standard D-Pad X Achse
AXIS_DPAD_Y = 7  # Standard D-Pad Y Achse

# Button-Indizes
BTN_A         = 0
BTN_B         = 1
BTN_BACK      = 4
BTN_START     = 6
BTN_LB        = 9   # Deadman Switch
BTN_RB        = 10  # Precision Mode
BTN_DPAD_UP   = 11
BTN_DPAD_DOWN = 12

ARM_JOINTS = ['joint_basis_arm1', 'joint_arm1_arm2',
              'joint_arm2_arm3', 'joint_arm3_greifer']

JOINT_LIMITS_FALLBACK = {
    'joint_basis_arm1':   (-6.17, 0.0),
    'joint_arm1_arm2':    (-2.04, 0.0),
    'joint_arm2_arm3':    (-2.42, 0.0),
    'joint_arm3_greifer': (-1.57, 1.57),
}

UPDATE_RATE_HZ = 50.0
JOINT_SPEED = 0.8  # rad/s base speed
PRECISION_MULTIPLIER = 0.3
DEADZONE = 0.1

class JoyToJoint4DoF(Node):
    def __init__(self):
        super().__init__('joy_to_joint_4dof')

        self.axes = []
        self.buttons = []
        self.prev_buttons = []
        self.latest_joint_state = None

        self.q_target = None
        self.initialized = False

        self.gripper_pos = 0.0
        self.gripper_target = 0.0

        self.deadman_enabled = False

        self.joint_limits = dict(JOINT_LIMITS_FALLBACK)
        self.urdf_ready = False

        qos_cmd = QoSProfile(depth=10, durability=DurabilityPolicy.VOLATILE, history=HistoryPolicy.KEEP_LAST)
        self.target_pub = self.create_publisher(JointState, '/servo_joint_target', qos_cmd)
        self.stm32_pub = self.create_publisher(String, '/stm32_cmd', qos_cmd)

        self.create_subscription(Joy, '/joy', self.joy_cb, 10)
        self.create_subscription(JointState, '/joint_states', self.js_cb, 10)

        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, history=HistoryPolicy.KEEP_LAST)
        self.create_subscription(String, '/robot_description', self.urdf_cb, qos)

        self.timer = self.create_timer(1.0 / UPDATE_RATE_HZ, self.control_loop)

        self.get_logger().info(
            'joy_to_joint_4dof | INTUITIVE JOINT CONTROL\n'
            '  LB halten       = Deadman (oder Back für Toggle)\n'
            '  RB halten       = Precision Mode (30% speed)\n'
            '  Linker Stick L/R= Basis drehen (Yaw, invertiert)\n'
            '  Linker Stick U/D= Arm 1 hoch/runter (Pitch 1)\n'
            '  Rechter Stick U/D = Arm 2 hoch/runter (Pitch 2)\n'
            '  Rechter Stick L/R = Greifer neigen (Pitch 3)\n'
            '  A / B           = Greifer auf / zu\n'
            '  Start           = home\n')

    def js_cb(self, msg):
        # CRITICAL FILTER: Only accept messages that contain our joint names.
        # Another middleware node publishes /joint_states using 'joint_1', 'joint_2', etc.
        # We must ignore those to avoid overwriting valid Unity feedback.
        if not msg.name or ARM_JOINTS[0] not in msg.name:
            return
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
            root = ET.fromstring(msg.data)
            for joint in root.findall('joint'):
                name = joint.get('name')
                if name in ARM_JOINTS:
                    lim = joint.find('limit')
                    if lim is not None and lim.get('lower') and lim.get('upper'):
                        self.joint_limits[name] = (float(lim.get('lower')), float(lim.get('upper')))
            self.urdf_ready = True
            self.get_logger().info('URDF parsed -- Limits ready.')
        except Exception as e:
            self.get_logger().error(f'URDF parsing failed: {e}')

    def _pressed(self, idx):
        if idx >= len(self.buttons): return False
        was = self.prev_buttons[idx] if idx < len(self.prev_buttons) else 0
        return self.buttons[idx] == 1 and was == 0

    def _raw_axis(self, idx):
        if idx >= len(self.axes): return 0.0
        v = self.axes[idx]
        return v if abs(v) > DEADZONE else 0.0

    def get_dpad_y(self):
        # 1. D-Pad als Achse (Standard für Xbox auf Linux ist Achse 7)
        if len(self.axes) > AXIS_DPAD_Y:
            val = self.axes[AXIS_DPAD_Y]
            if abs(val) > 0.1:
                return val
        
        # 2. Fallback: D-Pad als Buttons
        if len(self.buttons) > BTN_DPAD_DOWN:
            return float(self.buttons[BTN_DPAD_UP] - self.buttons[BTN_DPAD_DOWN])
            
        return 0.0

    def control_loop(self):
        if not self.buttons or self.latest_joint_state is None:
            return
        
        # Deadman Toggle
        if self._pressed(BTN_BACK):
            self.deadman_enabled = not self.deadman_enabled
            status = "ENABLED" if self.deadman_enabled else "DISABLED"
            self.get_logger().info(f'Deadman Toggle: {status}')

        if self._pressed(BTN_A):
            self._send_cmd('grip_open')
            self.gripper_target = 0.4
        if self._pressed(BTN_B):
            self._send_cmd('grip_close')
            self.gripper_target = 0.0
        if self._pressed(BTN_START):
            self._send_cmd('home')

        self.prev_buttons = list(self.buttons)

        # Smooth gripper
        dt = 1.0 / UPDATE_RATE_HZ
        gripper_speed = 0.5
        if self.gripper_pos < self.gripper_target:
            self.gripper_pos = min(self.gripper_target, self.gripper_pos + gripper_speed * dt)
        elif self.gripper_pos > self.gripper_target:
            self.gripper_pos = max(self.gripper_target, self.gripper_pos - gripper_speed * dt)

        # Init target
        if not self.initialized:
            cur = dict(zip(self.latest_joint_state.name, self.latest_joint_state.position))
            if all(j in cur for j in ARM_JOINTS):
                self.q_target = np.array([cur[j] for j in ARM_JOINTS])
                self.initialized = True
            return

        deadman_active = self.deadman_enabled or (len(self.buttons) > BTN_LB and self.buttons[BTN_LB] == 1)
        
        target_v = np.zeros(4)
        
        if not deadman_active:
            # We are NOT driving the robot. Continuously sync our internal target
            # to the actual robot state so we start from here when LB is pressed.
            cur = dict(zip(self.latest_joint_state.name, self.latest_joint_state.position))
            if all(j in cur for j in ARM_JOINTS):
                self.q_target = np.array([cur[j] for j in ARM_JOINTS])
            return # IMPORTANT: Do not publish when idle, otherwise we create an infinite echo loop with Unity!
        else:
            speed_mult = PRECISION_MULTIPLIER if (len(self.buttons) > BTN_RB and self.buttons[BTN_RB] == 1) else 1.0
            
            # Map Inputs directly to Joint Velocities (Sehr intuitiv!)
            target_v[0] = -self._raw_axis(AXIS_LEFTX) * JOINT_SPEED * speed_mult
            target_v[1] = self._raw_axis(AXIS_LEFTY) * JOINT_SPEED * speed_mult
            target_v[2] = self._raw_axis(AXIS_RIGHTY) * JOINT_SPEED * speed_mult
            target_v[3] = self._raw_axis(AXIS_RIGHTX) * JOINT_SPEED * speed_mult

        # Integrate and apply limits
        q_new = self.q_target + target_v * dt
        for i, jname in enumerate(ARM_JOINTS):
            lo, hi = self.joint_limits.get(jname, (-3.14, 3.14))
            q_new[i] = np.clip(q_new[i], lo, hi)

        self.q_target = q_new

        # Publish target
        out = JointState()
        out.header.stamp = self.get_clock().now().to_msg()
        out.name = list(ARM_JOINTS) + ['joint_greifer_finger1', 'joint_greifer_finger2', 'joint_greifer_finger3']
        out.position = [float(q) for q in q_new] + [self.gripper_pos] * 3
        self.target_pub.publish(out)

    def _send_cmd(self, text):
        msg = String()
        msg.data = text
        self.stm32_pub.publish(msg)
        # self.get_logger().info(f'/stm32_cmd -> {text}') # Auskommentiert um Spam zu vermeiden

def main(args=None):
    rclpy.init(args=args)
    node = JoyToJoint4DoF()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

