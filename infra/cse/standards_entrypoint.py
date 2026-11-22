"""Opt-in isolated real CSE MQTT profile; never changes the main demo volume."""
import configparser
from importlib.metadata import version
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import sys

from entrypoint import persistent_secret, stage_config
from patch_shutdown import verify_installed_patch


def main():
    patch=verify_installed_patch()
    config=configparser.ConfigParser(interpolation=None)
    config.optionxform=str
    config.read('/etc/fire-route/acme.ini')
    config['mqtt']={'enable':'True','address':'mqtt','port':'1883','timeout':'10'}
    config['mqtt.security']={'useTLS':'False'}
    data=io.StringIO();config.write(data)
    source=Path('/tmp/fire-route-mqtt.ini');source.write_text(data.getvalue())
    runtime=Path('/data')
    staged=stage_config(source,runtime,secret=persistent_secret(runtime))
    metadata={'implementation':'ACME','installed_version':version('acmecse'),
        'python':platform.python_version(),'machine':platform.machine(),
        'config_sha256':hashlib.sha256(staged.read_bytes()).hexdigest(),
        'deployment':'ISOLATED_STANDALONE_IN_CSE_NOT_MEC',
        'bindings':['HTTP','MQTT'],'TLS':False,'shutdown_patch':patch}
    Path('/metadata').mkdir(exist_ok=True)
    Path('/metadata/cse.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps({'phase':'ISOLATED_STANDARDS_CSE_STARTUP','version':metadata['installed_version'],
                      'bindings':metadata['bindings']}),flush=True)
    os.execv(sys.executable,[sys.executable,'-m','acmecse','-dir',str(runtime),
        '--config',staged.name,'--no-remote-cse','--mqtt'])

if __name__=='__main__':main()
