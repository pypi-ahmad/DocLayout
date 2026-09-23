"""Optional CPU deployment of this checkout. Requires Modal; deploying is explicit."""

from pathlib import Path

import modal

app = modal.App("doclayout-gpt6-sol")
project_root = Path(__file__).resolve().parents[1]
image = (
    modal.Image.debian_slim(python_version="3.14")
    .pip_install("uv")
    .add_local_dir(project_root / "doclayout", "/app/doclayout", copy=True)
    .add_local_file(project_root / "pyproject.toml", "/app/pyproject.toml", copy=True)
    .add_local_file(project_root / "uv.lock", "/app/uv.lock", copy=True)
    .add_local_file(project_root / "README.md", "/app/README.md", copy=True)
    .add_local_file(project_root / "LICENSE", "/app/LICENSE", copy=True)
    .workdir("/app")
    .run_commands("uv sync --frozen --group dev")
)


@app.function(
    image=image, secrets=[modal.Secret.from_name("doclayout-openai")], timeout=900
)
@modal.asgi_app()
def api():
    from doclayout.scripts.server import app as server

    return server
