"""
unity_twin.launch.py — Lean launch for the standalone Unity Digital Twin.

No MoveIt, no stm32_serial_node, no ros2_control.
Unity is the hardware: subscribes to /servo_joint_target, publishes /joint_states.

Starts:
  1. rosbridge_server       — WebSocket bridge to Unity (port 9090)
  2. robot_state_publisher  — /robot_description + /tf from /joint_states
                               Reads URDF directly — no moveit_configs_utils.

The world->Basis TF is already in the URDF as joint_world_basis (fixed),
so robot_state_publisher handles it automatically.

Run Xbox teleop separately:
  ros2 launch xbox_servo_teleop servo_teleop.launch.py
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import AnyLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description():
    # Load URDF directly — avoids any moveit_configs_utils dependency
    urdf_path = os.path.join(
        get_package_share_directory("roboterarm_description"),
        "urdf", "Roboterarm.urdf",
    )
    with open(urdf_path, "r") as f:
        robot_description = f.read()

    # 1. rosbridge WebSocket server (Unity <-> ROS)
    rosbridge_launch = IncludeLaunchDescription(
        AnyLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory("rosbridge_server"),
                "launch", "rosbridge_websocket_launch.xml",
            )
        ),
        launch_arguments={"port": "9090"}.items(),
    )

    # 2. QoS relay: rosbridge publishes /joint_states with RELIABLE+TRANSIENT_LOCAL.
    #    RSP subscribes with BEST_EFFORT+VOLATILE. Fast-DDS does not bridge these.
    #    This relay re-publishes with VOLATILE QoS on /joint_states_rsp.
    relay_node = Node(
        package="roboterarm_config",
        executable="joint_states_relay",
        name="joint_states_relay",
        output="screen",
    )

    # 3. robot_state_publisher — reads from relay topic (VOLATILE, compatible)
    rsp_node = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        parameters=[{"robot_description": robot_description}],
        remappings=[("/joint_states", "/joint_states_rsp")],
        output="screen",
    )

    # 4. Static TF: world -> Basis (explicit, avoids startup race with RSP)
    world_tf_node = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name="world_to_basis_tf",
        arguments=["0", "0", "0", "0", "0", "0", "world", "Basis"],
    )

    return LaunchDescription([
        rosbridge_launch,
        relay_node,
        rsp_node,
        world_tf_node,
    ])