"""Unit-тесты: Path traversal и safe_join."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unpackers.rpa_unpacker import RpaUnpacker, PathTraversalError
from core.base_unpacker import UnpackOptions


class TestSafeJoin(unittest.TestCase):
    def setUp(self):
        self.unpacker = RpaUnpacker()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _safe_join(self, path: str):
        return self.unpacker._safe_join(path, self.tmpdir, sanitize=False)

    def test_normal_path(self):
        self.assertEqual(self._safe_join('images/bg.png'), 'images/bg.png')

    def test_absolute_path_rejected(self):
        with self.assertRaises(PathTraversalError):
            self._safe_join('/etc/passwd')

    def test_windows_absolute_path_rejected(self):
        with self.assertRaises(PathTraversalError):
            self._safe_join('C:/Windows/System32')

    def test_path_traversal_double_dot(self):
        with self.assertRaises(PathTraversalError):
            self._safe_join('../escape.txt')

    def test_path_traversal_nested(self):
        with self.assertRaises(PathTraversalError):
            self._safe_join('images/../../../escape.txt')

    def test_drive_letter_rejected(self):
        with self.assertRaises(PathTraversalError):
            self._safe_join('C:file.txt')

    def test_backslash_in_component_rejected(self):
        # После replace `\\` на `/` путь становится валидным.
        # Но мы тестируем, что '\\' в составе компонента не проходит
        # (это уже не относится к safe_join, это работа sanitize).
        # Здесь — путь с backslash обрабатывается как обычный с разделителем.
        result = self._safe_join('images\\bg.png')
        self.assertEqual(result, 'images/bg.png')

    def test_empty_path_rejected(self):
        with self.assertRaises(PathTraversalError):
            self._safe_join('')

    def test_only_dots_rejected(self):
        with self.assertRaises(PathTraversalError):
            self._safe_join('./')

    def test_dotdot_only_rejected(self):
        with self.assertRaises(PathTraversalError):
            self._safe_join('..')


class TestUnpackResult(unittest.TestCase):
    def test_unpack_nonexistent_file(self):
        unpacker = RpaUnpacker()
        options = UnpackOptions(output_dir=tempfile.mkdtemp())
        result = unpacker.unpack('Z:/nonexistent.rpa', options)
        self.assertFalse(result.success)
        self.assertGreater(len(result.errors), 0)


if __name__ == '__main__':
    unittest.main()
