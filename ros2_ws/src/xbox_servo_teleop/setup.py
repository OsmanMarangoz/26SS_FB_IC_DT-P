import os
from glob import glob
from setuptools import setup

package_name = 'xbox_servo_teleop'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='robopi2',
    maintainer_email='robopi2@todo.todo',
    description='Xbox TCP teleoperation for Roboterarm_mit_Objs',
    license='MIT',
    entry_points={
        'console_scripts': [
            # Weg B (aktiv): Jacobian / Damped Least Squares
            'joy_to_tcp_jac_node = xbox_servo_teleop.joy_to_tcp_jac_node:main',
            # Alt (Position-IK, behalten als Fallback):
            'joy_to_tcp_ik_node = xbox_servo_teleop.joy_to_tcp_ik_node:main',
        ],
    },
)