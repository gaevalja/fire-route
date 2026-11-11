"""Stage an owned runtime config, record identity, then exec the actual CSE.

ACME accepts a filename, not a path, in --config. Runtime staging deliberately
does not overwrite a user's existing acme.ini or another configuration file.
"""
from importlib.metadata import distributions, version
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
from datetime import datetime, timezone

def stage_config(source: Path, runtime: Path) -> Path:
    """Create a content-addressed managed file; preserve all existing files."""
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    runtime.mkdir(parents=True, exist_ok=True)
    target = runtime / ("fire-route-" + digest + ".ini")
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if target.is_symlink() or target.read_bytes() != data:
            raise RuntimeError("Managed runtime config differs; refusing to overwrite")
    else:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
    return target


def command_for(config: Path, runtime: Path) -> list[str]:
    if config.parent.resolve() != runtime.resolve():
        raise ValueError("CSE config must be staged inside its runtime directory")
    return [sys.executable, "-m", "acmecse", "-dir", str(runtime),
            "--config", config.name, "--no-remote-cse", "--no-mqtt"]


def main() -> None:
    source = Path("/etc/fire-route/acme.ini")
    runtime = Path("/data")
    config = stage_config(source, runtime)
    metadata = {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "implementation": "ACME", "installed_version": version("acmecse"),
        "python": platform.python_version(), "machine": platform.machine(),
        "config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
        "runtime_config_filename": config.name,
        "installed_distributions": sorted(f"{d.metadata['Name']}=={d.version}" for d in distributions()),
        "deployment": "standalone_dev_IN_CSE_NOT_MEC",
    }
    Path("/metadata").mkdir(parents=True, exist_ok=True)
    Path("/metadata/cse.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({"phase": "CSE_STARTUP", "implementation": "ACME",
                      "version": metadata["installed_version"], "config_filename": config.name}), flush=True)
    command = command_for(config, runtime)
    os.execv(sys.executable, command)


if __name__ == "__main__":
    main()
