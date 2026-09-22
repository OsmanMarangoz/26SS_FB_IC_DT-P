# 26SS_FB_IC_DT-P

This project uses LeRobot to train a custom robotic arm for pick-and-place. Unity provides the simulation environment, while a real robot is used for deployment. Using an ACT model, the arm learns to pick up a Lego brick and place it into a bin.

[![LeRobot imitation learning - Pick and place in Unity](https://img.youtube.com/vi/Q3-prXXEQCo/0.jpg)](https://youtu.be/Q3-prXXEQCo)


For the .venv and lerobot please:

# 1. Create a fresh virtual environment
python3 -m venv --system-site-packages .venv

# 2. Activate it (Mac/Linux)
source .venv/bin/activate
# (Or on Windows: .venv\Scripts\activate)

# 3. Install the packages from your recipe
pip install -r requirements.txt

pip install -e /home/robopi2/lerobot_ws/lerobot
pip intsall -e /home/robopi2/lerobot_ws/lerobot_robot_nema_arm

verfiy lerobot install:

python3 -c "from lerobot_robot_nema_arm import NemaArm, NemaArmConfig; print('yo it works')"