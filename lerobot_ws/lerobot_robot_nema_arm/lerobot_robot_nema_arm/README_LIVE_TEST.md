# Live-Test von `InfectV22/nema_gamepad_extended` auf dem echten Arm

Dataset: 45 Episoden, 16627 Frames, 15 FPS, per Gamepad in der Unity-Simulation
aufgenommen. Action/State-Features (`joint_basis_arm1.pos`, …, 7 Joints)
passen 1:1 auf `NemaArm` (`robot_type: "nema"`) — es ist also mit genau dieser
Robot-Klasse aufgenommen worden.

---

## Mode-Auswahl: Twin vs. Real

Das System unterstützt zwei Modi, die mit `--mode` gewählt werden:

| | **Twin Mode** (`--mode twin`) | **Real Mode** (`--mode real`) |
|---|---|---|
| **Arm** | Unity Digital Twin | Physischer Arm (STM32) |
| **Kameras** | ROS2Camera (sensor_msgs/Image via rosbridge) | ReCamera (USB/RTSP) |
| **Kamera-Topics** | `/unity/camera_top/image_raw`, `/unity/camera_side/image_raw` | — (direkt USB/RTSP) |
| **Benötigt Unity** | ✅ Ja | ❌ Nein |
| **Benötigt physischen Arm** | ❌ Nein | ✅ Ja |
| **Benötigt rosbridge** | ✅ Ja | ❌ Nein |

---

## Twin-Mode Startup (3 Terminals)

### Terminal 1: ROS2 Bridge + TF

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch roboterarm_config unity_twin.launch.py
```

### Terminal 2: Xbox Teleop

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch xbox_servo_teleop servo_teleop.launch.py
```

### Terminal 3: LeRobot Recording

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
source ~/lerobot_ws/.venv/bin/activate

HF_USER=pixelouie
python3 manual_record.py --mode twin --repo_id=${HF_USER}/nema_test_v3 --fps=15
```

### Unity Setup

Unity muss laufen mit:
- `RosConnector` verbunden zum Pi (WebSocket port 9090)
- `RobotStateReceiver` subscribed auf `/servo_joint_target`
- `JointStatePublisher` publiziert `/joint_states`
- `UnityRosImagePublisher` publiziert Kamera-Bilder (Inspector: TopRenderTexture + SideRenderTexture zuweisen)

### Kamera-Topics prüfen

```bash
# Topic-Typ (muss sensor_msgs/msg/Image sein)
ros2 topic type /unity/camera_top/image_raw
ros2 topic type /unity/camera_side/image_raw

# Frequenz (sollte ~15 Hz sein)
ros2 topic hz /unity/camera_top/image_raw
ros2 topic hz /unity/camera_side/image_raw
```

---

## Real-Mode Startup

### Terminal 1: STM32 Bridge

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 run roboterarm_config stm32_serial_node.py --ros-args \
    --params-file ~/ros2_ws/src/roboterarm_config/config/stm32_calibration.yaml \
    -p serial_port:=/dev/ttyACM0
```

Prüfen: `ros2 topic echo /joint_states` sollte Daten zeigen.

### Terminal 2: Xbox Teleop

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch xbox_servo_teleop servo_teleop.launch.py
```

### Terminal 3: LeRobot Recording

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
source ~/lerobot_ws/.venv/bin/activate

HF_USER=pixelouie
python3 manual_record.py --mode real --repo_id=${HF_USER}/nema_real_v1 --fps=15
```

---

## Recording Controls

| Taste | Aktion |
|---|---|
| `s` | Episode **STARTEN** (Aufnahme beginnt) |
| `e` | Episode **BEENDEN** und speichern |
| `r` | Aktuelle Episode **VERWERFEN** (neu aufnehmen) |
| `q` | Alles **beenden** und zu HuggingFace hochladen |

Optionen:
- `--no_camera` — ohne Kamera testen (kein Bild in Dataset)
- `--no_push` — nicht zu HuggingFace hochladen
- `--fps=15` — Aufnahme-Frequenz (Standard 15)
- `--task="Move arm left to right"` — Task-Beschreibung

---

## Troubleshooting

### Fehlende Kamera-Topics

**Symptom:** `ros2 topic list` zeigt `/unity/camera_top/image_raw` nicht

**Ursachen:**
1. Unity läuft nicht oder ist nicht mit rosbridge verbunden
2. `UnityRosImagePublisher` Komponente fehlt im Unity-Projekt
3. RenderTextures nicht zugewiesen im Inspector
4. rosbridge_server läuft nicht (port 9090)

**Lösung:**
- Unity Console auf `[ImagePublisher]` Fehler prüfen
- `ros2 topic list | grep unity` ausführen
- rosbridge_server Logs prüfen

### Timeout bei Kamera-Verbindung

**Symptom:** `[ROS2Camera] Kein Bild auf '/unity/camera_top/image_raw' nach 10s`

**Ursachen:**
1. Unity publiziert noch nicht (Startup-Reihenfolge)
2. FPS zu niedrig eingestellt in Unity
3. Netzwerkproblem zwischen Pi und Unity-Rechner

**Lösung:**
- `ros2 topic hz /unity/camera_top/image_raw` prüfen
- Unity `publishFps` erhöhen (mindestens 15)
- Netzwerk-Ping prüfen

### Falsches Encoding

**Symptom:** Bilder sehen farblich falsch aus

**Lösung:**
- `UnityRosImagePublisher` publiziert immer `rgb8` (korrekt)
- Falls andere Quelle: encoding auf `rgb8`, `bgr8`, `rgba8` oder `bgra8` setzen

---

## Phase 1 — Open-Loop Replay

### 1.1 Hardware bringen (nur STM32-Bridge, kein Unity/MoveIt nötig)

Die Dataset-Aktionen liegen bereits im Joint-Space vor, es muss also nichts
neu geplant werden — `unity_moveit_bridge` und MoveIt werden für reines Replay
**nicht** gebraucht, nur der serielle Bridge-Node:

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 run roboterarm_config stm32_serial_node.py --ros-args \
    --params-file ~/ros2_ws/src/roboterarm_config/config/stm32_calibration.yaml \
    -p serial_port:=/dev/ttyACM0
```

Prüfen, ob es läuft: `ros2 topic echo /joint_states` sollte Daten zeigen.

### 1.2 Replay starten

Neues Script: [`replay_dataset.py`](replay_dataset.py) (analog zu
`manual_record.py`, gleiche Sicherheits-Konventionen).

```bash
source /home/robopi2/ros2_ws/.venv/bin/activate

# Trockenlauf OHNE Hardware — nur Dataset-Ladepfad testen:
python3 replay_dataset.py --episode=0 --dry_run --yes

# Eine Episode auf dem echten Arm, mit Homing davor:
python3 replay_dataset.py --episode=0 --home

# Alle 45 Episoden nacheinander (mit Bestätigung vor jeder Episode):
python3 replay_dataset.py --all --home
```

---

## Phase 2 — Policy trainieren & Closed-Loop deployen

### 2.1 Training (braucht GPU)

```bash
lerobot-train \
    --dataset.repo_id=InfectV22/nema_gamepad_extended \
    --policy.type=act \
    --policy.device=cuda \
    --output_dir=outputs/train/nema_act \
    --job_name=nema_act \
    --policy.repo_id=<HF_USER>/nema_act_v1
```

### 2.2 Closed-Loop auf dem echten Arm

```bash
lerobot-rollout \
    --robot.type=nema_arm \
    --policy.type=act \
    --policy.path=<HF_USER>/nema_act_v1  \
    --fps=15
```

---

## Zusammenfassung / Nächste Schritte

- [x] `replay_dataset.py` gebaut + gegen echtes Dataset dry-run-getestet
- [x] Twin-Mode: Unity-Kameras → ROS2Camera → LeRobot Recording
- [x] Real-Mode: ReCamera (USB/RTSP) → LeRobot Recording
- [x] `--mode twin` / `--mode real` Switch implementiert
- [x] `UnityRosImagePublisher.cs` für Unity erstellt
- [ ] STM32 anschließen, Replay live gegen Hardware fahren
- [ ] Training auf GPU-Maschine anstoßen
- [ ] `lerobot-rollout` für Closed-Loop-Test auf dem Pi
