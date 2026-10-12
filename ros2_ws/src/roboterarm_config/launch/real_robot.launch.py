"""
real_robot.launch.py — Launch file for physical robot arm operation.

Starts:
  1. stm32_serial_node       — Serial bridge to STM32F446RE (publishes /joint_states,
                               subscribes to /servo_joint_target and /stm32_cmd)
  2. joint_states_relay      — QoS bridge for Fast-DDS (/joint_states -> /joint_states_rsp)
  3. robot_state_publisher   — Loads Roboterarm URDF -> /tf
  4. world_to_basis_tf       — Static transform: world -> Basis
  5. (Optional) Xbox teleop  — If launch_teleop:=true, runs game_controller_node +
                               joy_to_tcp_jac_4dof_node

Usage:
  ros2 launch roboterarm_config real_robot.launch.py
  (and in second terminal: ros2 launch xbox_servo_teleop servo_teleop.launch.py)
  OR:
  ros2 launch roboterarm_config real_robot.launch.py launch_teleop:=true
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    roboterarm_config_dir = get_package_share_directory("roboterarm_config")
    roboterarm_desc_dir = get_package_share_directory("roboterarm_description")

    urdf_path = os.path.join(roboterarm_desc_dir, "urdf", "Roboterarm.urdf")
    with open(urdf_path, "r") as f:
        robot_description = f.read()

    calibration_file = os.path.join(roboterarm_config_dir, "config", "stm32_calibration.yaml")

    launch_teleop_arg = DeclareLaunchArgument(
        "launch_teleop",
        default_value="false",
        description="Launch Xbox teleop nodes together with the robot hardware"
    )
    serial_port_arg = DeclareLaunchArgument(
        "serial_port",
        default_value="/dev/ttyACM0",
        description="Serial port for STM32 microcontroller"
    )

    # 1. STM32 Serial Bridge
    stm32_node = Node(
        package="roboterarm_config",
        executable="stm32_serial_node.py",
        name="stm32_serial_node",
        output="screen",
        parameters=[
            calibration_file,
            {"serial_port": LaunchConfiguration("serial_port")},
            {"baud_rate": 115200},
        ],
    )

    # 2. QoS Relay for RSP
    relay_node = Node(
        package="roboterarm_config",
        executable="joint_states_relay",
        name="joint_states_relay",
        output="screen",
    )

    # 3. Robot State Publisher
    rsp_node = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        parameters=[{"robot_description": robot_description}],
        remappings=[("/joint_states", "/joint_states_rsp")],
        output="screen",
    )

    # 4. Static TF: world -> Basis
    world_tf_node = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name="world_to_basis_tf",
        arguments=["0", "0", "0", "0", "0", "0", "world", "Basis"],
    )

    # 5. Optional Xbox Teleop
    joy_node = Node(
        package="joy",
        executable="game_controller_node",
        name="xbox_joy",
        output="screen",
        parameters=[{"deadzone": 0.05, "autorepeat_rate": 20.0}],
        condition=IfCondition(LaunchConfiguration("launch_teleop")),
    )

    teleop_node = Node(
        package="xbox_servo_teleop",
        executable="joy_to_tcp_jac_4dof_node",
        name="joy_to_tcp_jac_4dof",
        output="screen",
        condition=IfCondition(LaunchConfiguration("launch_teleop")),
    )

    return LaunchDescription([
        launch_teleop_arg,
        serial_port_arg,
        stm32_node,
        relay_node,
        rsp_node,
        world_tf_node,
        joy_node,
        teleop_node,
    ])

