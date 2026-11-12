"""Local role access codes and short-lived opaque sessions; never CSE secrets."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
from threading import Lock
import time

ROLES = {'resident','responder'}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def write_private(path, value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:
        json.dump(value,stream,indent=2)
        stream.write('\n')


def prepare_access(directory: Path):
    directory.mkdir(parents=True,exist_ok=True)
    codes_path,auth_path=directory/'access-codes.json',directory/'auth.json'
    if codes_path.exists() and auth_path.exists():
        if codes_path.is_symlink() or codes_path.stat().st_mode&0o077:
            raise ValueError('Access codes must remain private')
        codes=json.loads(codes_path.read_text())
        expected={r:digest(codes[r]) for r in ROLES}
        if AuthStore.load(auth_path).hashes!=expected:
            raise ValueError('Existing access files disagree; refusing overwrite')
        return
    if codes_path.exists() or auth_path.exists():
        raise ValueError('Incomplete access files; refusing overwrite')
    codes={r:secrets.token_urlsafe(32) for r in ROLES}
    write_private(codes_path,codes)
    write_private(auth_path,{r:digest(codes[r]) for r in ROLES})


@dataclass
class Session:
    role: str
    expires: float


class AuthStore:
    def __init__(self, hashes, *, lifetime=1200, clock=time.monotonic):
        if set(hashes)!=ROLES or any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for v in hashes.values()):
            raise ValueError('Invalid role credential hashes')
        self.hashes,self.lifetime,self.clock=hashes,lifetime,clock
        self.sessions,self.attempts={},{}
        self.lock=Lock()

    @classmethod
    def load(cls,path):
        if Path(path).is_symlink() or Path(path).stat().st_mode&0o077:
            raise ValueError('Role credential file must be private and regular')
        return cls(json.loads(Path(path).read_text()))

    def login(self,role,code,peer):
        with self.lock:
            now=self.clock()
            self.sessions={k:s for k,s in self.sessions.items() if s.expires>now}
            self.attempts={k:v for k,v in self.attempts.items() if now-v[0]<60}
            since,count=self.attempts.get(peer,(now,0))
            if count>=5:
                return None,'RATE_LIMITED'
            self.attempts[peer]=(since,count+1)
            supplied=digest(code) if isinstance(code,str) and len(code)<=256 else ''
            valid=isinstance(role,str) and role in ROLES and secrets.compare_digest(supplied,self.hashes.get(role,''))
            if not valid:
                return None,'UNAUTHORIZED'
            self.attempts.pop(peer,None)
            token=secrets.token_urlsafe(32)
            self.sessions[digest(token)]=Session(role,now+self.lifetime)
            return token,'OK'

    def role(self,token):
        if not isinstance(token,str) or len(token)>256:return None
        with self.lock:
            session=self.sessions.get(digest(token))
            return session.role if session and session.expires>self.clock() else None

    def logout(self,token):
        with self.lock:self.sessions.pop(digest(token),None)


def main():
    prepare_access(Path('.runtime'))
    print('Private access files ready in .runtime/; access codes are not printed.')


if __name__=='__main__':main()
