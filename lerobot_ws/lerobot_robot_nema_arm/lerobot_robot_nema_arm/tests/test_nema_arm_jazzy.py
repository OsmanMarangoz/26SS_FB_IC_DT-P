from lerobot_robot_nema_arm import NemaArm, NemaArmConfig

config = NemaArmConfig()
robot = NemaArm(config)

print("observation_features:", robot.observation_features)
print("action_features:", robot.action_features)
print("is_connected:", robot.is_connected)

robot.connect()
print("Verbunden!")

import time
for i in range(10):
    obs = robot.get_observation()
    print(f"[{i}] {obs}")
    time.sleep(0.5)

robot.disconnect()