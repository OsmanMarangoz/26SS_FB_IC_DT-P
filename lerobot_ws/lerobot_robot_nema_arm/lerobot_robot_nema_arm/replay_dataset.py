"""
replay_dataset.py — Spielt aufgezeichnete Dataset-Episoden auf dem ECHTEN NEMA Arm ab.

Open-Loop Replay: Nimmt ein LeRobotDataset (z.B. InfectV22/nema_gamepad_extended,
per Gamepad in der Unity-Simulation aufgenommen) und sendet die aufgezeichneten
Joint-Aktionen 1:1 an den echten Arm — OHNE Policy, OHNE MoveIt/Unity, OHNE Kamera.

Zweck: Hardware-Sanity-Check — bewegt sich der echte Arm so wie in der Aufnahme?
Das ist der erste Schritt vor einem Policy-Training (siehe README_LIVE_TEST.md).

Voraussetzung: stm32_serial_node muss laufen und mit dem STM32 verbunden sein.
    Minimal-Start (OHNE Unity/MoveIt nötig — die Aktionen kommen direkt aus dem
    Dataset im Joint-Space, es wird nicht neu geplant):

        source /opt/ros/jazzy/setup.bash
        source ~/ros2_ws/install/setup.bash
        ros2 run roboterarm_config stm32_serial_node.py --ros-args \
            --params-file ~/ros2_ws/src/roboterarm_config/config/stm32_calibration.yaml \
            -p serial_port:=/dev/ttyACM0

Start:
    source /opt/ros/jazzy/setup.bash
    source ~/ros2_ws/install/setup.bash
    source ~/ros2_ws/.venv/bin/activate

    # 1) Trockenlauf OHNE Hardware — nur prüfen ob Dataset lädt + Aktionen stimmen:
    python3 replay_dataset.py --episode=0 --dry_run

    # 2) Einzelne Episode auf dem echten Arm abspielen:
    python3 replay_dataset.py --episode=0 --home

    # 3) Alle Episoden nacheinander (mit Bestätigung vor jeder):
    python3 replay_dataset.py --all --home

Sicherheit:
    - Vor jeder Episode: Countdown + Bestätigung (mit --yes überspringbar)
    - --home: sendet vorher "home"-Kommando ans STM32 (definierte Startpose)
    - Strg+C: sendet "estop", trennt sauber
    - Kamera ist standardmäßig AUS (nicht nötig für Replay). Mit --camera einschalten.
"""

import argparse
import time

from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.utils.constants import ACTION

from lerobot_robot_nema_arm import NemaArm, NemaArmConfig

# ── ANSI Farben ─────────────────────────────────────────────────────────────
GREEN, YELLOW, RED, CYAN, BOLD, RESET = (
    "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
)


def banner(text, color):
    line = "═" * 56
    print(f"\n{color}{BOLD}{line}\n  {text}\n{line}{RESET}\n")


def replay_episode(robot, dataset: LeRobotDataset, fps: float, dry_run: bool) -> None:
    actions = dataset.select_columns(ACTION)
    action_names = dataset.features[ACTION]["names"]

    for idx in range(dataset.num_frames):
        loop_start = time.perf_counter()

        action_array = actions[idx][ACTION]
        action = {name: float(action_array[i]) for i, name in enumerate(action_names)}

        if dry_run:
            print(f"  frame {idx:4d}/{dataset.num_frames}: {action}")
        else:
            robot.get_observation()  # gleiche Pipeline wie lerobot-replay (Prozessor-kompatibel)
            robot.send_action(action)

        elapsed = time.perf_counter() - loop_start
        if elapsed < 1.0 / fps:
            time.sleep(1.0 / fps - elapsed)


def confirm_or_skip(text: str, skip: bool) -> bool:
    if skip:
        return True
    answer = input(f"{YELLOW}{text} [j/N] {RESET}").strip().lower()
    return answer in ("j", "y", "yes", "ja")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo_id", default="InfectV22/nema_gamepad_extended")
    parser.add_argument("--root", default=None, help="lokaler Cache-Pfad (optional)")
    parser.add_argument("--episode", type=int, default=0, help="einzelne Episode abspielen")
    parser.add_argument("--all", action="store_true", help="alle Episoden nacheinander abspielen")
    parser.add_argument("--fps", type=float, default=None, help="überschreibt Dataset-FPS")
    parser.add_argument("--home", action="store_true", help="vor jeder Episode 'home'-Kommando senden")
    parser.add_argument("--camera", action="store_true", help="Kamera verbinden (für Replay nicht nötig)")
    parser.add_argument("--yes", action="store_true", help="Bestätigungen überspringen")
    parser.add_argument("--dry_run", action="store_true", help="nur ausgeben, nichts an die Hardware senden")
    args = parser.parse_args()

    banner("LADE DATASET METADATEN...", CYAN)
    meta_probe = LeRobotDataset(args.repo_id, root=args.root, episodes=[0])
    total_episodes = meta_probe.meta.total_episodes
    fps = args.fps or meta_probe.fps
    print(f"Dataset: {args.repo_id}  |  {total_episodes} Episoden  |  {fps} FPS")

    episode_indices = list(range(total_episodes)) if args.all else [args.episode]
    for ep in episode_indices:
        if ep < 0 or ep >= total_episodes:
            raise ValueError(f"Episode {ep} existiert nicht (0..{total_episodes - 1}).")

    robot = None
    if not args.dry_run:
        banner("VERBINDE ROBOT...", CYAN)
        robot = NemaArm(NemaArmConfig(use_camera=args.camera))
        robot.connect()

    try:
        for ep in episode_indices:
            if not confirm_or_skip(f"Episode {ep} JETZT auf dem echten Arm abspielen?", args.yes):
                banner(f"Episode {ep} übersprungen", YELLOW)
                continue

            if args.home and robot is not None:
                robot.send_command("home")
                time.sleep(2.0)

            if not args.dry_run:
                banner(f"🔴 EPISODE {ep} — 3s...", RED)
                time.sleep(3.0)

            dataset = LeRobotDataset(args.repo_id, root=args.root, episodes=[ep])
            banner(f"▶ SPIELE EPISODE {ep} AB ({dataset.num_frames} Frames)", GREEN)
            replay_episode(robot, dataset, fps, args.dry_run)
            banner(f"✅ EPISODE {ep} FERTIG", GREEN)

    except KeyboardInterrupt:
        banner("⚠ ABGEBROCHEN — sende E-Stop", RED)
        if robot is not None:
            robot.send_command("estop")
    finally:
        if robot is not None:
            robot.disconnect()

    banner("FERTIG", CYAN)


if __name__ == "__main__":
    main()
