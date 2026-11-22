"""Stage an owned runtime config, record identity, then exec the actual CSE.

ACME accepts a filename, not a path, in --config. Runtime staging deliberately
does not overwrite a user's existing acme.ini or another configuration file.
"""
from importlib.metadata import distributions, version
import configparser
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import secrets
import stat
import sys
import tempfile
from datetime import datetime, timezone

def persistent_secret(runtime: Path) -> str:
    """Publish once atomically; never rotate or print an existing volume key."""
    runtime.mkdir(parents=True,exist_ok=True)
    target=runtime/'fire-route.secret'
    if not target.exists() and not target.is_symlink():
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(dir=runtime,prefix='.secret-',delete=False) as stream:
                temporary=Path(stream.name)
                stream.write((secrets.token_hex(32)+'\n').encode('ascii'))
                stream.flush();os.fsync(stream.fileno())
            try:os.link(temporary,target,follow_symlinks=False)
            except FileExistsError:pass
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)
    try:
        fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
                    or info.st_uid!=os.getuid() or info.st_size>65):
                raise RuntimeError('Unsafe persistent CSE secret file')
            value=stream.read(66).decode('ascii').strip()
    except (OSError,UnicodeError):
        raise RuntimeError('Cannot read private persistent CSE secret') from None
    if not re.fullmatch(r'[0-9a-f]{64}',value):
        raise RuntimeError('Invalid persistent CSE secret; refusing rotation')
    return value


def stage_config(source: Path, runtime: Path, *, secret: str | None = None) -> Path:
    """Create a content-addressed managed file; preserve all existing files."""
    data = source.read_bytes()
    if secret is not None:
        if not re.fullmatch(r'[0-9a-f]{64}',secret):raise ValueError('Invalid CSE secret format')
        parser=configparser.ConfigParser(interpolation=None)
        parser.optionxform=str
        parser.read_string(data.decode('utf-8'))
        parser.set('basic.config','secret',secret)
        output=io.StringIO();parser.write(output)
        data=output.getvalue().encode('utf-8')
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
    from patch_shutdown import verify_installed_patch
    shutdown_patch=verify_installed_patch()
    source = Path("/etc/fire-route/acme.ini")
    runtime = Path("/data")
    config = stage_config(source, runtime,secret=persistent_secret(runtime))
    metadata = {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "implementation": "ACME", "installed_version": version("acmecse"),
        "python": platform.python_version(), "machine": platform.machine(),
        "config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
        "runtime_config_filename": config.name,
        "installed_distributions": sorted(f"{d.metadata['Name']}=={d.version}" for d in distributions()),
        "deployment": "standalone_dev_IN_CSE_NOT_MEC",
        "secret_configured": True,
        "secret_policy": "persistent_private_volume_file",
        "shutdown_patch": shutdown_patch,
    }
    Path("/metadata").mkdir(parents=True, exist_ok=True)
    Path("/metadata/cse.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({"phase": "CSE_STARTUP", "implementation": "ACME",
                      "version": metadata["installed_version"], "config_filename": config.name,
                      "shutdown_patch": shutdown_patch["patch_id"]}), flush=True)
    command = command_for(config, runtime)
    os.execv(sys.executable, command)


if __name__ == "__main__":
    main()
