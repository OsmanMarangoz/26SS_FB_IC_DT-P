# 26SS_FB_IC_DT-P
if you fresh intall the project u might need to add this pacakge and import the robot new.
and the remove it it is not needed for running or stuff.
in manifest.json and packages-lock.json add your local path for the udrf-importer package.
the package can be cloned here:

git clone https://github.com/Unity-Technologies/URDF-Importer

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