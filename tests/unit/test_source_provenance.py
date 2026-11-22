import tempfile
from pathlib import Path
import unittest
from backend.evidence import source_identity

class SourceProvenanceTests(unittest.TestCase):
    def test_optional_transport_config_and_Dockerfiles_change_identity(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'infra').mkdir()
            names=['compose.standards.yaml','compose.https.yaml','compose.mec-local.yaml','compose.mec-runtime.yaml','compose.mec-services.yaml','infra/mosquitto.conf','infra/core.Dockerfile','infra/couch_health.sh']
            for name in names:(root/name).write_text('original')
            before=source_identity(root)
            self.assertEqual(set(before['source_files']),set(names))
            (root/'infra/mosquitto.conf').write_text('changed')
            self.assertNotEqual(source_identity(root)['source_manifest_sha256'],before['source_manifest_sha256'])

    def test_private_runtime_files_never_enter_source_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'.runtime').mkdir();(root/'.runtime/access-codes.json').write_text('PRIVATE')
            self.assertEqual(source_identity(root)['source_files'],{})
