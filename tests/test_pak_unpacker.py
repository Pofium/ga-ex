"""Тесты для UnrealPakUnpacker."""
import os
import struct
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unpackers.pak_unpacker import (
    UnrealPakUnpacker,
    UNREAL_PAK_MAGIC,
    UNREAL_PAK_FOOTER_MAGIC,
    get_unreal_pak_encryption_info,
    normalize_unreal_aes_key,
)


def make_footer_pak(size: int = 256, footer_size: int = 44, version: int = 8) -> bytes:
    """Создаёт синтетический `.pak` с магией в footer, а не в начале."""
    if size <= footer_size:
        raise ValueError('size must be greater than footer_size')
    data = bytearray(b'\x00' * size)
    pos = size - footer_size
    data[pos:pos + 4] = struct.pack('<I', UNREAL_PAK_FOOTER_MAGIC)
    data[pos + 4:pos + 8] = struct.pack('<I', version)
    return bytes(data)


def make_encrypted_footer_pak(size: int = 512) -> bytes:
    """Создаёт синтетический Unreal `.pak` c footer v12 и encrypted index."""
    footer_size = 221
    if size <= footer_size:
        raise ValueError('size must be greater than footer_size')

    data = bytearray(b'\x00' * size)
    pos = size - footer_size
    guid = bytes.fromhex('11223344556677889900AABBCCDDEEFF')
    data[pos:pos + 16] = guid
    data[pos + 16] = 1  # encrypted index
    data[pos + 17:pos + 21] = struct.pack('<I', UNREAL_PAK_FOOTER_MAGIC)
    data[pos + 21:pos + 25] = struct.pack('<I', 11)  # v12 stored as 11
    return bytes(data)


class TestDetect(unittest.TestCase):
    """Тесты детекта .pak файлов."""

    def test_detect_magic(self):
        """Детект работает с правильной магией."""
        with tempfile.NamedTemporaryFile(suffix='.pak', delete=False) as f:
            f.write(UNREAL_PAK_MAGIC + b'\x00' * 100)
            path = f.name
        try:
            self.assertTrue(UnrealPakUnpacker.detect(path))
        finally:
            os.unlink(path)

    def test_detect_wrong_magic(self):
        """Детект не срабатывает на неправильной магии."""
        with tempfile.NamedTemporaryFile(suffix='.pak', delete=False) as f:
            f.write(b'XXXX' + b'\x00' * 100)
            path = f.name
        try:
            self.assertFalse(UnrealPakUnpacker.detect(path))
        finally:
            os.unlink(path)

    def test_detect_footer_magic(self):
        """Детект работает и для UE4/UE5 `.pak`, где магия лежит в footer."""
        with tempfile.NamedTemporaryFile(suffix='.pak', delete=False) as f:
            f.write(make_footer_pak())
            path = f.name
        try:
            self.assertTrue(UnrealPakUnpacker.detect(path))
        finally:
            os.unlink(path)

    def test_detect_wrong_extension(self):
        """Детект не срабатывает на файлах без расширения .pak."""
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(UNREAL_PAK_MAGIC + b'\x00' * 100)
            path = f.name
        try:
            self.assertFalse(UnrealPakUnpacker.detect(path))
        finally:
            os.unlink(path)

    def test_detect_nonexistent(self):
        """Детект не падает на несуществующих файлах."""
        self.assertFalse(UnrealPakUnpacker.detect('/nonexistent/file.pak'))


class TestAnalyze(unittest.TestCase):
    """Тесты метода analyze."""

    def test_analyze_non_pak_file(self):
        """analyze возвращает detected=False для не-pak файлов."""
        with tempfile.NamedTemporaryFile(suffix='.pak', delete=False) as f:
            f.write(b'NOTAPAK' + b'\x00' * 100)
            path = f.name
        try:
            u = UnrealPakUnpacker()
            info = u.analyze(path)
            self.assertFalse(info['detected'])
            self.assertEqual(info['type'], 'unreal_pak')
        finally:
            os.unlink(path)

    def test_analyze_reads_encrypted_footer_info(self):
        """analyze видит зашифрованный индекс и encryption guid из footer."""
        with tempfile.NamedTemporaryFile(suffix='.pak', delete=False) as f:
            f.write(make_encrypted_footer_pak())
            path = f.name
        try:
            u = UnrealPakUnpacker()
            info = u.analyze(path)
            self.assertTrue(info['detected'])
            self.assertTrue(info['is_encrypted_index'])
            self.assertEqual(info['version'], 12)
            self.assertEqual(
                info['encryption_guid'],
                '11223344556677889900aabbccddeeff',
            )
        finally:
            os.unlink(path)


class TestHelpers(unittest.TestCase):
    """Тесты вспомогательных функций Unreal AES."""

    def test_get_unreal_pak_encryption_info(self):
        """Флаг encrypted index читается напрямую из footer."""
        with tempfile.NamedTemporaryFile(suffix='.pak', delete=False) as f:
            f.write(make_encrypted_footer_pak())
            path = f.name
        try:
            info = get_unreal_pak_encryption_info(path)
            self.assertTrue(info['detected'])
            self.assertTrue(info['is_encrypted_index'])
            self.assertEqual(info['version'], 12)
        finally:
            os.unlink(path)

    def test_normalize_unreal_aes_key(self):
        """AES-ключ нормализуется к виду `0x...`."""
        key = 'c3aec3423c1676d9cfa5a5f3cb81ddf95ce7df7b79ccfb0de58cf48a5947395a'
        self.assertEqual(
            normalize_unreal_aes_key(key),
            '0xC3AEC3423C1676D9CFA5A5F3CB81DDF95CE7DF7B79CCFB0DE58CF48A5947395A',
        )

    def test_normalize_unreal_aes_key_rejects_short_value(self):
        """Короткий AES-ключ отклоняется."""
        with self.assertRaises(ValueError):
            normalize_unreal_aes_key('1234')


class TestUnpack(unittest.TestCase):
    """Тесты метода unpack."""

    def test_unpack_non_pak_returns_error(self):
        """unpack возвращает ошибку для не-pak файлов."""
        with tempfile.NamedTemporaryFile(suffix='.pak', delete=False) as f:
            f.write(b'NOTAPAK' + b'\x00' * 100)
            path = f.name
        try:
            with tempfile.TemporaryDirectory() as out_dir:
                from core.base_unpacker import UnpackOptions
                u = UnrealPakUnpacker()
                opts = UnpackOptions(output_dir=out_dir)
                r = u.unpack(path, opts)
                self.assertFalse(r.success)
                self.assertGreater(len(r.errors), 0)
                # Should mention "не похоже на .pak"
                self.assertTrue(any('не похоже' in e for e in r.errors))
        finally:
            os.unlink(path)


if __name__ == '__main__':
    unittest.main()
