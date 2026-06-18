"""
manual_record.py — Datenaufnahme mit MANUELLER Tastensteuerung über SSH.

Funktioniert headless (kein Display nötig) — liest Tasten direkt aus dem
SSH-Terminal. LeRobot beobachtet passiv: eure Unity/Xbox-Pipeline steuert
den Arm, dieses Script nimmt Beobachtung + Aktion auf.

Tasten während der Aufnahme:
    s   = Episode STARTEN (Aufnahme beginnt)
    e   = Episode BEENDEN und speichern
    r   = aktuelle Episode VERWERFEN (neu aufnehmen)
    q   = alles beenden und zu HuggingFace hochladen

Start:
    source /opt/ros/jazzy/setup.bash
    source ~/ros2_ws/install/setup.bash
    source ~/lerobot_ws/.venv/bin/activate

    HF_USER=pixelouie
    python3 manual_record.py --repo_id=${HF_USER}/nema_test_v3 --fps=15
"""

import argparse
import select
import sys
import termios
import time
import tty

from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.utils.feature_utils import build_dataset_frame, hw_to_dataset_features

from lerobot_robot_nema_arm import (
    NemaArm, NemaArmConfig,
    UnityTeleoperator, UnityTeleoperatorConfig,
)

# ── ANSI Farben ─────────────────────────────────────────────────────────────
GREEN, YELLOW, RED, CYAN, BOLD, RESET = (
    "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
)


def banner(text, color):
    line = "═" * 56
    print(f"\n{color}{BOLD}{line}\n  {text}\n{line}{RESET}\n")


# ── Non-blocking Tastatureingabe über SSH-Terminal ──────────────────────────
class KeyReader:
    """Liest einzelne Tasten ohne Enter, non-blocking. Funktioniert über SSH."""

    def __enter__(self):
        self._fd = sys.stdin.fileno()
        self._old = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        return self

    def __exit__(self, *args):
        termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)

    def get_key(self):
        dr, _, _ = select.select([sys.stdin], [], [], 0)
        if dr:
            return sys.stdin.read(1).lower()
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo_id", required=True, help="z.B. pixelouie/nema_test_v3")
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--task", default="Move arm left to right")
    parser.add_argument("--no_camera", action="store_true", help="ohne Kamera testen")
    parser.add_argument("--no_push", action="store_true", help="nicht zu HuggingFace hochladen")
    args = parser.parse_args()

    # ── Robot + Teleop verbinden ────────────────────────────────────────────
    banner("VERBINDE ROBOT + TELEOP...", CYAN)
    robot = NemaArm(NemaArmConfig(use_camera=not args.no_camera))
    teleop = UnityTeleoperator(UnityTeleoperatorConfig())

    robot.connect()
    teleop.connect()

    # ── Dataset erstellen ────────────────────────────────────────────────────
    action_features = hw_to_dataset_features(robot.action_features, "action", True)
    obs_features = hw_to_dataset_features(robot.observation_features, "observation", True)
    dataset_features = {**action_features, **obs_features}

    dataset = LeRobotDataset.create(
        repo_id=args.repo_id,
        fps=args.fps,
        features=dataset_features,
        robot_type=robot.name,
        use_videos=True,
    )

    banner("BEREIT", GREEN)
    print(f"{BOLD}Tasten:{RESET}")
    print(f"  {GREEN}s{RESET} = Episode STARTEN")
    print(f"  {YELLOW}e{RESET} = Episode BEENDEN + speichern")
    print(f"  {RED}r{RESET} = Episode VERWERFEN (neu)")
    print(f"  {CYAN}q{RESET} = beenden + hochladen")
    print(f"\nDataset: {args.repo_id}  |  {args.fps} FPS\n")

    frame_period = 1.0 / args.fps
    episode_count = 0

    with KeyReader() as keys:
        recording = False
        quit_requested = False

        while not quit_requested:
            loop_start = time.perf_counter()
            key = keys.get_key()

            # ── IDLE: warte auf Start ──────────────────────────────────────
            if not recording:
                if key == "s":
                    recording = True
                    banner(f"🔴 EPISODE {episode_count} LÄUFT — JETZT BEWEGEN", GREEN)
                elif key == "q":
                    quit_requested = True
                else:
                    time.sleep(0.05)
                continue

            # ── RECORDING: Frames aufnehmen ────────────────────────────────
            if key == "e":
                dataset.save_episode()
                banner(f"💾 EPISODE {episode_count} GESPEICHERT", YELLOW)
                episode_count += 1
                recording = False
                print(f"{BOLD}'s' für nächste Episode, 'q' zum Beenden{RESET}")
                continue

            if key == "r":
                try:
                    dataset.clear_episode_buffer()
                except Exception:
                    pass
                banner(f"🗑  EPISODE {episode_count} VERWORFEN", RED)
                recording = False
                print(f"{BOLD}'s' für neuen Versuch{RESET}")
                continue

            # Frame aufnehmen (LeRobot beobachtet nur — kein send_action!)
            obs = robot.get_observation()
            action = teleop.get_action()

            obs_frame = build_dataset_frame(dataset.features, obs, prefix="observation")
            action_frame = build_dataset_frame(dataset.features, action, prefix="action")
            frame = {**obs_frame, **action_frame, "task": args.task}
            dataset.add_frame(frame)

            # FPS halten
            elapsed = time.perf_counter() - loop_start
            if elapsed < frame_period:
                time.sleep(frame_period - elapsed)

    # ── Aufräumen + Upload ───────────────────────────────────────────────────
    banner(f"FERTIG — {episode_count} Episoden aufgenommen", CYAN)
    robot.disconnect()
    teleop.disconnect()

    if episode_count > 0 and not args.no_push:
        banner("LADE ZU HUGGINGFACE HOCH...", CYAN)
        dataset.push_to_hub()
        banner(f"✅ HOCHGELADEN: {args.repo_id}", GREEN)
    else:
        banner("Nicht hochgeladen (keine Episoden oder --no_push)", YELLOW)


if __name__ == "__main__":
    main()