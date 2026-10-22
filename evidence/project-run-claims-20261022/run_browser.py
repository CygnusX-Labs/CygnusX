import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

root = Path(__file__).resolve().parents[2]
out = Path(__file__).resolve().parent
handle = json.loads((out / "runtime-handle.json").read_text())
context = json.loads((Path(handle["private_root"]) / "context.json").read_text())
context["fixtures"] = json.loads((Path(handle["private_root"]) / "fixtures.json").read_text())
image = subprocess.check_output([
    "docker", "image", "inspect", "cygnusx-ri095-browser:v1.49.0", "--format", "{{.Id}}"
], text=True).strip()
resultdir = Path(tempfile.mkdtemp(prefix="cygnusx-run-claims-browser-"))
os.chmod(resultdir, 0o777)
command = [
    "docker", "run", "--rm", "-i", "--name", "cygnusx-run-claims-browser-20261022",
    "--network", "host", "--user", "10001:10001", "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges:true", "--security-opt",
    "seccomp=" + str(root / "deploy/acceptance/seccomp-browser.json"),
    "--read-only", "--tmpfs", "/tmp:rw,nosuid,size=512m", "--shm-size", "512m",
    "-v", str(out) + ":/work:ro", "-v", str(resultdir) + ":/output",
    image, "node", "/work/browser.cjs",
]
result = subprocess.run(command, input=json.dumps(context), text=True, capture_output=True)
(out / "browser.log").write_text(result.stdout + result.stderr)
for path in resultdir.iterdir():
    shutil.copy2(path, out / ("browser-" + path.name))
print("Browser exit code:", result.returncode)
print((out / "browser.log").read_text()[-1500:])
if (out / "browser-results.json").exists():
    print((out / "browser-results.json").read_text())
raise SystemExit(result.returncode)
