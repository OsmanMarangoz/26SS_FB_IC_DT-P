# 26SS_FB_IC_DT-P

This project uses LeRobot to train a custom robotic arm for pick-and-place. Unity provides the simulation environment, while a real robot is used for deployment. Using an ACT model, the arm learns to pick up a Lego brick and place it into a bin.

[![LeRobot imitation learning - Pick and place in Unity](https://img.youtube.com/vi/Q3-prXXEQCo/0.jpg)](https://youtu.be/Q3-prXXEQCo)


## Installation

1. **Create a virtual environment**

	```bash
	python3 -m venv --system-site-packages .venv
	```

2. **Activate the environment**

	```bash
	source .venv/bin/activate
	# Windows: .venv\Scripts\activate
	```

3. **Install the project dependencies**

	```bash
	pip install -r requirements.txt
	pip install -e /home/robopi2/lerobot_ws/lerobot
	pip install -e /home/robopi2/lerobot_ws/lerobot_robot_nema_arm
	```

4. **Verify the LeRobot installation**

	```bash
	python3 -c "from lerobot_robot_nema_arm import NemaArm, NemaArmConfig; print('LeRobot installation works')"
	```