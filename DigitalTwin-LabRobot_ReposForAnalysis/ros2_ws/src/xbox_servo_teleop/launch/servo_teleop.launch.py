"""
servo_teleop.launch.py
Xbox TCP-Teleoperation (Weg B: Jacobian/DLS) fuer Roboterarm_mit_Objs.

Startet nur:
  1. game_controller_node  (Xbox via SDL2)
  2. joy_to_tcp_jac_node    (Jacobian -> /servo_joint_target)

Voraussetzung: euer Unity/Robot-Launch laeuft bereits in einem anderen Terminal
(liefert /robot_description, /joint_states, tf, stm32_serial_node).
"""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='joy',
            executable='game_controller_node',
            name='xbox_joy',
            output='screen',
            parameters=[{'deadzone': 0.05, 'autorepeat_rate': 20.0}],
        ),
        Node(
            package='xbox_servo_teleop',
            executable='joy_to_tcp_jac_node',
            name='joy_to_tcp_jac',
            output='screen',
        ),
    ])