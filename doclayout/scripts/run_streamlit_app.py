# Modified for DocLayout; see NOTICE for a summary of changes.
import os
import subprocess
import sys
from importlib.util import find_spec


def streamlit_app_cli(app_name: str = "streamlit_app.py"):
    if find_spec("streamlit") is None:
        raise SystemExit(
            "The GUI needs the 'gui' extra. Reinstall DocLayout with [gui]; see the README installation steps."
        )
    argv = sys.argv[1:]
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(cur_dir, app_name)
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        app_path,
        "--server.address",
        "127.0.0.1",
        "--server.fileWatcherType",
        "none",
        "--server.headless",
        "true",
    ]
    if argv:
        cmd += ["--"] + argv
    raise SystemExit(
        subprocess.run(cmd, env={**os.environ, "IN_STREAMLIT": "true"}).returncode
    )
