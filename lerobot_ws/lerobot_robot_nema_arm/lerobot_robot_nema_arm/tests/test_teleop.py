from lerobot_robot_nema_arm import UnityTeleoperator, UnityTeleoperatorConfig
import time

teleop = UnityTeleoperator(UnityTeleoperatorConfig())
teleop.connect()

print("Jetzt Ball in Unity bewegen...")
for i in range(10):
    action = teleop.get_action()
    print(f"[{i}] {action}")
    time.sleep(0.5)

teleop.disconnect()