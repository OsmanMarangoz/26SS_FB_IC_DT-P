This short README explains how to install the two lerobot packages in editable mode so you can develop against them.

Prerequisite
- Create and activate a Python virtual environment (recommended). This ensures packages are installed into the local environment so editable installs use the local libs. Use `--system-site-packages` to also access system-installed apt packages and libraries:

  python3 -m venv --system-site-packages .venv
  source .venv/bin/activate

Install (two simple ways)
- Install by pointing `pip` at each package path from the workspace root:

  python3 -m pip install -e lerobot_ws/lerobot
  python3 -m pip install -e lerobot_robot_nema_arm/lerobot_robot_nema_arm

- Or install from inside each package directory:

  cd lerobot_ws/lerobot
  python -m pip install -e .

  cd ../../lerobot_robot_nema_arm/lerobot_robot_nema_arm
  python -m pip install -e .

Notes
- Using `python3 -m pip` ensures you install into the active interpreter / virtualenv.
- Editable installs (`-e`) let you modify source files without reinstalling.

If you want, I can also add this to an existing README or make it more detailed.
