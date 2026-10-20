#!/usr/bin/env python3
"""Install the current workspace as a macOS login service (local paper only)."""

from pathlib import Path
import os
import plistlib
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    directory = Path.home()/"Library/LaunchAgents"
    directory.mkdir(parents=True, exist_ok=True)
    label = "com.quantit.paper"
    path = directory/f"{label}.plist"
    payload = {
        "Label": label,
        "ProgramArguments": [sys.executable, str(root/"scripts/run_service.py")],
        "WorkingDirectory": str(root), "RunAtLoad": True, "KeepAlive": True,
        "ThrottleInterval": 10,
        "EnvironmentVariables": {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "QUANTIT_RUNNER": "1", "QUANTIT_CLOSELOOP": "1", "QUANTIT_US_SOURCE": "yahoo",
            "QUANTIT_RUNNER_EVAL_SEC": "1800",
        },
        "StandardOutPath": "/dev/null", "StandardErrorPath": "/dev/null",
    }
    for key in ("CLOSELOOP_DATA_DIR", "CLOSELOOP_ARTIFACTS"):
        if os.environ.get(key):
            payload["EnvironmentVariables"][key] = os.environ[key]
    path.write_bytes(plistlib.dumps(payload))
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{label}"], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", domain, str(path)], check=True)
    print(path)


if __name__ == "__main__":
    main()
