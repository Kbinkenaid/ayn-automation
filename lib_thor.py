"""Shared infrastructure for Thor provisioning: lockfile, debounce, logging,
adb runner with disconnect detection, backups, atomic writes, state I/O.
stdlib only."""
import atexit
import contextlib
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
STATE_DIR = Path(os.environ.get("THOR_STATE_DIR", Path.home() / ".thor-provision"))
LOCK = STATE_DIR / ".lock"
LOG_DIR = STATE_DIR / "logs"

# exit codes (v2 §4.3)
EX_OK, EX_PARTIAL, EX_PRECOND, EX_ABORTED, EX_LOCKED = 0, 1, 2, 3, 4


def utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Lock:
    """PID-stamped lockfile; steals stale locks from dead PIDs."""

    def __init__(self):
        self.acquired = False

    def __enter__(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if LOCK.exists():
            try:
                pid, ts = LOCK.read_text().split()
                os.kill(int(pid), 0)  # raises if dead
                raise SystemExit(f"another provision run is active (pid {pid}, started {ts})")
            except (ValueError, ProcessLookupError, PermissionError):
                print(f"note: stole stale lock from dead process", file=sys.stderr)
        LOCK.write_text(f"{os.getpid()} {utc()}")
        self.acquired = True
        return self

    def __exit__(self, *exc):
        if self.acquired and LOCK.exists():
            LOCK.unlink()


class Debounce:
    """Suppress repeat triggers for the same serial within `seconds`."""

    def __init__(self, seconds: int = 60):
        self.seconds = seconds
        self.path = STATE_DIR / "last-run.json"

    def check(self, serial: str) -> bool:
        """True if this trigger should be suppressed."""
        try:
            data = json.loads(self.path.read_text())
        except Exception:
            return False
        last = data.get(serial)
        if not last:
            return False
        then = datetime.datetime.fromisoformat(last)
        return (datetime.datetime.now(datetime.timezone.utc) - then).total_seconds() < self.seconds

    def mark(self, serial: str):
        try:
            data = json.loads(self.path.read_text())
        except Exception:
            data = {}
        data[serial] = utc()
        self.path.write_text(json.dumps(data))


class Logger:
    """Full command log to file; summary to console."""

    def __init__(self, serial: str):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.path = LOG_DIR / f"{utc().replace(':', '')}-{serial}.log"
        self._fh = open(self.path, "a")

    def cmd(self, line: str, out: str = "", err: str = "", rc: int | None = None):
        self._fh.write(f"$ {line}\n")
        if out:
            self._fh.write(out.rstrip() + "\n")
        if err:
            self._fh.write("[stderr] " + err.rstrip() + "\n")
        if rc is not None:
            self._fh.write(f"[rc={rc}]\n")
        self._fh.flush()

    def note(self, text: str):
        self._fh.write(f"# {text}\n")
        self._fh.flush()

    def close(self):
        self._fh.close()


@contextlib.contextmanager
def logger_for(serial: str):
    lg = Logger(serial)
    try:
        yield lg
    finally:
        lg.close()


class Adb:
    """adb wrapper: logs everything, detects mid-run disconnects."""

    def __init__(self, serial: str, log: Logger, dry: bool = False):
        self.serial = serial
        self.log = log
        self.dry = dry

    def _base(self) -> list[str]:
        adb = shutil.which("adb") or "/opt/homebrew/share/android-commandlinetools/platform-tools/adb"
        return [adb, "-s", self.serial]

    def run(self, *args, timeout: int = 120, check: bool = True) -> tuple[int, str, str]:
        line = " ".join(self._base() + list(args))
        self.log.cmd(line)
        if self.dry:
            self.log.note("dry-run: skipped")
            return 0, "", ""
        p = subprocess.run(self._base() + list(args), capture_output=True, text=True, timeout=timeout)
        self.log.cmd("", out=p.stdout, err=p.stderr, rc=p.returncode)
        if check and p.returncode != 0:
            raise RuntimeError(f"adb {' '.join(args)} failed rc={p.returncode}: {p.stderr.strip()[:300]}")
        return p.returncode, p.stdout.strip(), p.stderr.strip()

    def shell(self, cmd: str, **kw) -> tuple[int, str, str]:
        out = self.run("shell", cmd, **kw)
        # device vanished mid-command surfaces as closed transport
        if "device offline" in out[2] or "not found" in out[2].lower():
            raise ConnectionError(f"device lost during: {cmd}")
        return out

    # --- verified primitives (v2 §4.2 contract) ---

    def settings_put_verified(self, namespace: str, key: str, value: str) -> bool:
        self.shell(f"settings put {namespace} {key} {value}")
        _, got, _ = self.shell(f"settings get {namespace} {key}")
        return got == value

    def appops_allow_verified(self, pkg: str, op: str) -> bool:
        self.shell(f"appops set {pkg} {op} allow", check=False)
        _, got, _ = self.shell(f"appops get {pkg} {op}", check=False)
        return "allow" in got.lower()

    def install_verified(self, apk: Path, pkg: str) -> tuple[bool, str]:
        rc, out, err = self.run("install", "-r", "-g", str(apk), timeout=600)
        if rc != 0:
            return False, (err or out).strip()[:200]
        _, ver, _ = self.shell(f"dumpsys package {pkg} | grep -m1 versionName", check=False)
        ok = bool(ver.strip())
        return ok, ver.replace("versionName=", "").strip("'") or "unknown"

    def push_dir_verified(self, local: Path, remote: str) -> dict:
        rc, out, err = self.run("push", str(local), remote, timeout=3600)
        pushed_files = 0
        pushed_bytes = 0
        import re as _re
        m = _re.search(r"(\d+) files? pushed.*?([\d.]+) (MB|KB|GB|B)", err or out)
        if m:
            pushed_files = int(m.group(1))
        sampled_ok = True
        files = [p for p in sorted(local.rglob("*")) if p.is_file()]
        for f in files[: min(5, len(files))]:  # checksum sample
            rel = f.relative_to(local)
            r, lo, _ = self.shell(f"sha256sum '{remote}/{rel}'".replace("//", "/"), check=False)
            want = hashlib.sha256(f.read_bytes()).hexdigest()
            if not lo.startswith(want):
                sampled_ok = False
                break
        return {"files": pushed_files, "sample_ok": sampled_ok}

    def pull_file(self, remote: str, local: Path, timeout: int = 300):
        local.parent.mkdir(parents=True, exist_ok=True)
        return self.run("pull", remote, str(local), timeout=timeout)


# ---------- filesystem helpers ----------

def backup_file(path: Path, keep: int = 5) -> Path | None:
    if not path.exists():
        return None
    bak = path.with_suffix(path.suffix + f".bak.{utc().replace(':', '')}")
    shutil.copy2(path, bak)
    baks = sorted(path.parent.glob(path.name + ".bak.*"))
    for old in baks[:-keep]:
        old.unlink(missing_ok=True)
    return bak


def atomic_write(path: Path, data: str):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data)
    tmp.replace(path)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_state() -> dict:
    p = STATE_DIR / "state.json"
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def save_state(state: dict):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write(STATE_DIR / "state.json", json.dumps(state, indent=2))


atexit.register(lambda: LOCK.unlink() if LOCK.exists() else None)
