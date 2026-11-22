"""Bash HTTP-status fixtures, not execution of an actual CouchDB container."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'infra/mec/couch_health.sh'


@unittest.skipUnless(shutil.which('bash'),'Bash is required by the CouchDB image')
class CouchHealthTests(unittest.TestCase):
    def probe(self, response):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'response';path.write_bytes(response)
            return subprocess.run(['bash','-ec','source "$1"; couch_read_status 3<"$2"',
                'couch-unit',str(SCRIPT),str(path)],capture_output=True,timeout=4)

    def test_native_HTTP_200_up_status_is_accepted(self):
        self.assertEqual(self.probe(b'HTTP/1.1 200 OK\r\n').returncode,0)

    def test_failure_redirect_malformed_or_missing_status_is_not_healthy(self):
        for body in [b'',b'HTTP/1.1 503 Service Unavailable\r\n',b'HTTP/1.1 401 Unauthorized\r\n',
                     b'HTTP/1.1 302 Found\r\n',b'HTTP/1.1 2000 Wrong\r\n',b'garbage\r\n']:
            with self.subTest(body=body):self.assertNotEqual(self.probe(body).returncode,0)

    def test_health_script_has_valid_bash_syntax(self):
        result=subprocess.run(['bash','-n',str(SCRIPT)],capture_output=True)
        self.assertEqual(result.returncode,0)
