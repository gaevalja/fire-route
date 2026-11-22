"""Build-copy-only patch: replace upstream hardcoded Couch auth with configuration."""
from pathlib import Path


def patched(source):
    original = 'Username: "admin", Password: "admin"'
    if source.count(original) != 2 or source.count('"context"') != 1:
        raise ValueError('Reviewed upstream Couch auth patch context changed')
    return source.replace('"context"', '"context"\n\t"os"').replace(
        original, 'Username: os.Getenv("COUCHDB_USER"), Password: os.Getenv("COUCHDB_PASSWORD")')


if __name__ == '__main__':
    path = Path('/src/go-packages/meep-couch/db.go')
    path.write_text(patched(path.read_text()))
