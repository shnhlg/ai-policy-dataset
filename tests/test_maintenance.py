import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from normalize_csv_headers import normalize


class HeaderCleanupTests(unittest.TestCase):
    def test_matching_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.csv'
            path.write_text('id,text,text\n1,body,body\n', encoding='utf-8-sig')
            self.assertTrue(normalize(path))
            with path.open(encoding='utf-8-sig', newline='') as handle:
                self.assertEqual(list(csv.reader(handle)), [['id','text'],['1','body']])
            self.assertFalse(normalize(path))

    def test_conflict_leaves_input_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.csv'
            original = b'id,text,text\n1,old,new\n'
            path.write_bytes(original)
            with self.assertRaises(ValueError): normalize(path)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_invalid_width_leaves_input_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.csv'
            original = b'id,text,text\n1,body\n'
            path.write_bytes(original)
            with self.assertRaises(ValueError): normalize(path)
            self.assertEqual(path.read_bytes(), original)
