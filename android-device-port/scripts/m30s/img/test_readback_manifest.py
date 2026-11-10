from pathlib import Path
import hashlib
import tempfile
import unittest


class ReadbackManifestTests(unittest.TestCase):
    def hash_file(self, path):
        module = Path(__file__).with_name('make_readback_manifest.py')
        self.assertTrue(module.is_file(), 'Raw readback-window manifest generation is missing')
        from make_readback_manifest import hash_file
        return hash_file(path, 4096)

    def test_last_partial_window_and_full_stream_hash(self):
        data = b'A' * 4096 + b'B' * 4096 + b'C' * 2048
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'raw'; path.write_bytes(data)
            result = self.hash_file(path)
            self.assertEqual(result['sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual([w['offset_bytes'] for w in result['windows']], [0, 4096, 8192])
            self.assertEqual([w['length_bytes'] for w in result['windows']], [4096, 4096, 2048])
            for window in result['windows']:
                a = window['offset_bytes']; b = a + window['length_bytes']
                self.assertEqual(window['sha256'], hashlib.sha256(data[a:b]).hexdigest())

    def test_one_corrupted_window_changes_full_hash_and_only_that_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'raw'; path.write_bytes(b'A' * 10240)
            original = self.hash_file(path)
            data = bytearray(path.read_bytes()); data[5123] = 66; path.write_bytes(data)
            changed = self.hash_file(path)
            self.assertNotEqual(original['sha256'], changed['sha256'])
            for i in range(3):
                self.assertEqual(original['windows'][i] == changed['windows'][i], i != 1)


if __name__ == '__main__':
    unittest.main()
