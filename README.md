# 26SS_FB_IC_DT-P

This international student research and development project is a collaboration between Karlsruhe University of Applied Sciences (HKA); the German University of Technology in Oman (GUtech); and the Universite de Sfax.

This project uses LeRobot to train a custom robotic arm for pick-and-place. Unity provides the simulation environment, while a real robot is used for deployment. Using an ACT model, the arm learns to pick up a Lego brick and place it into a bin.


<p align="center">
	<a href="https://youtu.be/Q3-prXXEQCo">
		<img src="https://img.youtube.com/vi/Q3-prXXEQCo/0.jpg" alt="LeRobot imitation learning - Pick and place in Unity">
	</a>
</p>


## Installation
It is imprtant to note that the unity project is not on git. if needed you can message maos1011@h-ka.de.

1. **Create a virtual environment**

	```bash
	python3 -m venv --system-site-packages .venv
	```

2. **Activate the environment**

	```bash
	source .venv/bin/activate
    pip install -r requirements.txt
	```

3. **Install the project dependencies**
    
	```bash
    cd lerobot_ws
    git clone https://github.com/huggingface/lerobot.git
    
	pip install -e /lerobot
	pip install -e /lerobot_robot_nema_arm
	```

4. **Verify the LeRobot installation**

	```bash
	python3 -c "from lerobot_robot_nema_arm import NemaArm, NemaArmConfig; print('LeRobot installation works')"
	```

## How to launch

1. **start up unity. and enter play mode.**

2. **ros2 launch files**

In first terminal:
    ```bash
    ros2 launch roboterarm_config unity_twin.launch.py
    ```

In second terminal:
    ```bash
    ros2 launch xbox_servo_teleop servo_teleop.launch.py
    ```