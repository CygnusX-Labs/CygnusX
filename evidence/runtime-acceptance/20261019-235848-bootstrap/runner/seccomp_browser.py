"""Build the container-scoped seccomp profile that lets Chromium's real sandbox run.

Docker's default seccomp profile gates the namespace-creation syscalls behind
CAP_SYS_ADMIN. Chromium's normal Linux sandbox *is* a user-namespace sandbox, so
re-allowing those syscalls **enables the real sandbox** (never --no-sandbox) and
removes the need to grant any capability in this isolated disposable container.

The delta is: remove the single ``includes.caps == [CAP_SYS_ADMIN]`` gate, and
explicitly allow the small set of syscalls Chromium's namespace sandbox needs
(pivot_root/chroot/mount/keyring). All other default rules are preserved.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "docker-seccomp-default.json"
DST = HERE / "seccomp-browser.json"

SANDBOX_SYSCALLS = [
    "unshare",
    "clone",
    "clone3",
    "setns",
    "pivot_root",
    "chroot",
    "mount",
    "umount",
    "umount2",
    "mount_setattr",
    "move_mount",
    "open_tree",
    "setdomainname",
    "sethostname",
    "keyctl",
    "add_key",
    "request_key",
]


def build() -> dict:
    profile = json.loads(SRC.read_text())
    for block in profile["syscalls"]:
        if block.get("includes", {}).get("caps") == ["CAP_SYS_ADMIN"]:
            block.pop("includes")
    profile["syscalls"].insert(
        0,
        {
            "names": SANDBOX_SYSCALLS,
            "action": "SCMP_ACT_ALLOW",
            "comment": "RI095 acceptance: allow Chromium's user-namespace sandbox "
            "syscalls in this isolated disposable container (enables the sandbox)",
        },
    )
    return profile


if __name__ == "__main__":
    DST.write_text(json.dumps(build(), indent=2) + "\n")
    print(f"wrote {DST}")
