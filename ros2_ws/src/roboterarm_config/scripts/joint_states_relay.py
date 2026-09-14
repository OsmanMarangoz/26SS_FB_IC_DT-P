#!/usr/bin/env python3
"""
joint_states_relay.py

rosbridge publishes /joint_states with RELIABLE + TRANSIENT_LOCAL QoS.
robot_state_publisher subscribes with BEST_EFFORT + VOLATILE.
Fast-DDS does not deliver between these two in practice.

This relay bridges the gap:
  subscribes  /joint_states  with RELIABLE + TRANSIENT_LOCAL  (matches rosbridge)
  republishes /joint_states_rsp with RELIABLE + VOLATILE       (matches RSP)

unity_twin.launch.py remaps RSP's joint_states input to /joint_states_rsp.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from sensor_msgs.msg import JointState


SUB_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

PUB_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)


class JointStatesRelay(Node):
    def __init__(self):
        super().__init__('joint_states_relay')
        self._pub = self.create_publisher(JointState, '/joint_states_rsp', PUB_QOS)
        self._sub = self.create_subscription(
            JointState, '/joint_states', self._cb, SUB_QOS)
        self.get_logger().info(
            'joint_states_relay ready: /joint_states (TRANSIENT_LOCAL) '
            '→ /joint_states_rsp (VOLATILE)')

    def _cb(self, msg: JointState):
        self._pub.publish(msg)


def main():
    rclpy.init()
    node = JointStatesRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
