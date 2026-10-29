"""Exercise multiline CSV preservation, alias restoration, and corruption refusal."""
import contextlib
import gzip
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('shilin_data', Path(__file__).resolve().parents[1] / 'tools/data.py')
data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(data)

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.original_root = data.ROOT
        data.ROOT = self.root
        (self.root / 'source').mkdir()
        (self.root / 'metadata').mkdir()
        (self.root / 'source/frozen.txt').write_text('immutable source')
        header = b'id,text\r\n'
        self.body = header + '0001,"first\n第二行"\r\n'.encode() + b'9007199254740993,"a,b"\r\n'
        parts = []
        for i, body in enumerate([self.body[:self.body.index(b'900719')], header + self.body[self.body.index(b'900719'):]]):
            path = self.root / f'part-{i}.csv.gz'
            path.write_bytes(gzip.compress(body, mtime=0))
            parts.append({'path': path.name, 'sha256': data.digest(path), 'bytes': path.stat().st_size, 'rows': 1})
        self.table = {'id': 'p3_v6/registry', 'restore_path': 'original/registry.csv', 'sha256': hashlib.sha256(self.body).hexdigest(), 'bytes': len(self.body), 'rows': 2, 'columns': ['id', 'text'], 'header_bytes': len(header), 'parts': parts}
        self.alias = {k: v for k, v in self.table.items() if k not in ['parts', 'header_bytes']}
        self.alias.update(id='p3_v6/creation_events', alias_of=self.table['id'], restore_path='original/creation_events.csv')
        (self.root / 'metadata/tables.json').write_text(json.dumps({'tables': [self.table, self.alias]}))

    def tearDown(self):
        data.ROOT = self.original_root
        self.temp.cleanup()

    def test_multiline_unicode_long_integer_and_alias_restore_exactly(self):
        with contextlib.redirect_stdout(io.StringIO()):
            data.verify([self.table, self.alias], deep=True)
            data.restore([self.table, self.alias], self.root / 'restored')
        self.assertEqual((self.root / 'restored/original/registry.csv').read_bytes(), self.body)
        self.assertEqual((self.root / 'restored/original/creation_events.csv').read_bytes(), self.body)
        self.assertEqual((self.root / 'restored/frozen.txt').read_text(), 'immutable source')

    def test_tampered_shard_is_refused_before_destination_creation(self):
        (self.root / self.table['parts'][0]['path']).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'integrity failure'):
            data.restore([self.table], self.root / 'never_created')
        self.assertFalse((self.root / 'never_created').exists())

    def test_existing_output_is_preserved(self):
        target = self.root / 'existing'
        target.mkdir()
        (target / 'important.txt').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            data.restore([self.table], target)
        self.assertEqual((target / 'important.txt').read_text(), 'keep')

    def test_unknown_table_is_not_silently_ignored(self):
        with self.assertRaisesRegex(ValueError, 'Unknown tables'):
            data.selected('p3_v6', ['typo'])

if __name__ == '__main__':
    unittest.main()
