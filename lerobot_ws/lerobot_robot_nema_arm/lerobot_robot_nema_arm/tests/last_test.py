from lerobot_robot_nema_arm import NemaArm, NemaArmConfig
import time

config = NemaArmConfig(use_camera=True)  # use_camera=False zum Testen ohne Kamera
robot = NemaArm(config)
robot.connect()

for i in range(5):
    obs = robot.get_observation()
    print(f"[{i}] joints: {obs['joint_basis_arm1.pos']:.3f}")
    if 'cam_top' in obs:
        print(f"     cam: {obs['cam_top'].shape}")
    time.sleep(0.5)

robot.disconnect()