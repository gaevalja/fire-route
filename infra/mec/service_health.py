"""Local container health checks; no inferred protocol/deployment success."""
import json
from pathlib import Path
import sys
import time
from urllib.request import ProxyHandler, build_opener


def healthy(kind):
    if kind=='ipe':
        stamp=float(Path('/state/heartbeat').read_text())
        return 0<=time.time()-stamp<15 and Path('/state/connection.json').is_file()
    url={'risk':'http://127.0.0.1:8081/health','occupancy':'http://127.0.0.1:8082/health',
         'controller':'http://127.0.0.1/sandbox-ctrl/v1/applications'}[kind]
    with build_opener(ProxyHandler({})).open(url,timeout=3) as response:
        data=response.read(1024*1024+1)
        if response.status!=200 or len(data)>1024*1024:return False
        value=json.loads(data)
        return value.get('state')=='READY' if kind in {'risk','occupancy'} else value is None or isinstance(value,list)


if __name__=='__main__':
    try:ok=healthy(sys.argv[1])
    except Exception:ok=False
    raise SystemExit(0 if ok else 1)
