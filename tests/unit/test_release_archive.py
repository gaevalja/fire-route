"""No Docker or Git mutation; validate clean-reproduction archive boundary."""
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from infra.local_release import unpack_commit

def archive(name,kind=tarfile.REGTYPE):
    data=io.BytesIO()
    with tarfile.open(fileobj=data,mode='w') as t:
        m=tarfile.TarInfo(name);m.type=kind
        if kind==tarfile.REGTYPE:m.size=3;t.addfile(m,io.BytesIO(b'abc'))
        else:m.linkname='/tmp/escape';t.addfile(m)
    return data.getvalue()

class ReleaseArchiveTests(unittest.TestCase):
    def test_regular_file_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'release';unpack_commit(archive('backend/a.py'),root)
            self.assertEqual((root/'backend/a.py').read_bytes(),b'abc')
    def test_traversal_absolute_symlink_and_hardlink_never_extracted(self):
        for name,kind in [('../escape',tarfile.REGTYPE),('/escape',tarfile.REGTYPE),('link',tarfile.SYMTYPE),('hard',tarfile.LNKTYPE)]:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as d:
                root=Path(d)/'release'
                with self.assertRaises(ValueError):unpack_commit(archive(name,kind),root)
                self.assertEqual(list(root.iterdir()),[])
