"""Тесты для извлечения ключа CatSystem2 из exe."""
import os
import struct
import tempfile
import unittest

from core.gax_key_extractor import (
    find_gax_key_in_exe,
    is_catsystem2_exe,
    CS2_MARKERS,
)


class TestIsCatsystem2Exe(unittest.TestCase):
    """Проверка детекта CatSystem2 exe."""

    def test_non_cs2_file_returns_false(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.exe') as f:
            f.write(b'MZ\x90\x00' + b'\x00' * 100)
            path = f.name
        try:
            self.assertFalse(is_catsystem2_exe(path))
        finally:
            os.unlink(path)

    def test_cs2_marker_detected(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.exe') as f:
            # Записываем MZ header + CatScene marker в случайной позиции
            data = b'MZ' + b'\x00' * 500 + b'CatScene\x00' + b'\x00' * 100
            f.write(data)
            path = f.name
        try:
            self.assertTrue(is_catsystem2_exe(path))
        finally:
            os.unlink(path)

    def test_cs2_marker_int_detected(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.exe') as f:
            data = b'MZ' + b'\x00' * 100 + b'.int\x00' + b'\x00' * 100
            f.write(data)
            path = f.name
        try:
            self.assertTrue(is_catsystem2_exe(path))
        finally:
            os.unlink(path)

    def test_nonexistent_file_returns_false(self):
        self.assertFalse(is_catsystem2_exe('C:\\nonexistent\\path.exe'))

    def test_directory_returns_false(self):
        self.assertFalse(is_catsystem2_exe('C:\\'))


class TestFindGaxKey(unittest.TestCase):
    """Проверка поиска ключа в exe."""

    def test_no_cs2_marker_returns_none(self):
        """Без маркеров CS2 — ключ не найден."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.exe') as f:
            data = b'MZ' + b'\x00' * 1000
            f.write(data)
            path = f.name
        try:
            self.assertIsNone(find_gax_key_in_exe(path))
        finally:
            os.unlink(path)

    def test_with_marker_no_gax_returns_none(self):
        """Если есть маркер CS2, но нет .gax рядом — ключ не проверяется."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.exe') as f:
            data = b'MZ' + b'\x00' * 500 + b'CatScene' + b'\x00' * 100
            f.write(data)
            path = f.name
        try:
            # Без .gax рядом — функция вернёт None или None (нет sample для проверки)
            result = find_gax_key_in_exe(path)
            # Не нашли .gax → нечего проверять → None
            self.assertIsNone(result)
        finally:
            os.unlink(path)

    def test_nonexistent_file_returns_none(self):
        self.assertIsNone(find_gax_key_in_exe('C:\\nonexistent.exe'))


class TestGaxUnpackerWithExe(unittest.TestCase):
    """Проверка работы GaxUnpacker с опцией game_exe_path."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_unpack_with_fake_exe_saves_as_bin(self):
        """Если exe не подходит — файл сохраняется как .bin с warning."""
        from unpackers.gax_unpacker import GaxUnpacker
        from core.base_unpacker import UnpackOptions

        # Создаём синтетический .gax с нерасшифровываемыми данными
        gax_path = os.path.join(self.tmpdir, 'mystery.gax')
        with open(gax_path, 'wb') as f:
            f.write(b'\x00\x00\x00\x01' + b'\xde\xad\xbe\xef' * 50)

        # Создаём фейковый exe без маркеров CS2
        exe_path = os.path.join(self.tmpdir, 'game.exe')
        with open(exe_path, 'wb') as f:
            f.write(b'MZ' + b'\x00' * 100)

        out = os.path.join(self.tmpdir, 'out')
        os.makedirs(out, exist_ok=True)

        result = GaxUnpacker().unpack(
            gax_path,
            UnpackOptions(output_dir=out, game_exe_path=exe_path),
        )
        self.assertTrue(result.success)
        self.assertEqual(len(result.files_extracted), 1)
        self.assertTrue(result.files_extracted[0]['path'].endswith('.bin'))
        # Должен быть warning про exe
        self.assertTrue(any('exe' in w.lower() for w in result.warnings))


if __name__ == '__main__':
    unittest.main()
