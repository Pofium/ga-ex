"""Unit-тесты: FormatDetector."""
import os
import sys
import tempfile
import unittest
import struct
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.detector import FormatDetector, GameFormat
from unpackers.pak_unpacker import UNREAL_PAK_FOOTER_MAGIC


class TestFormatDetector(unittest.TestCase):
    def setUp(self):
        self.detector = FormatDetector()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_rpa(self, name: str, header: bytes) -> str:
        path = os.path.join(self.tmpdir, name)
        with open(path, 'wb') as f:
            f.write(header)
            f.write(b'\x00' * 100)
        return path

    def _create_footer_pak(self, name: str, size: int = 256, footer_size: int = 44) -> str:
        path = os.path.join(self.tmpdir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = bytearray(b'\x00' * size)
        pos = size - footer_size
        data[pos:pos + 4] = struct.pack('<I', UNREAL_PAK_FOOTER_MAGIC)
        data[pos + 4:pos + 8] = struct.pack('<I', 8)
        with open(path, 'wb') as f:
            f.write(data)
        return path

    def test_detect_rpa_30(self):
        path = self._create_rpa('test.rpa', b'RPA-3.0 0000000000000000 12345678\n')
        self.assertEqual(self.detector.detect_file(path), GameFormat.RENPY_RPA)

    def test_detect_rpa_20(self):
        path = self._create_rpa('test.rpa', b'RPA-2.0 0000000000000000\n')
        self.assertEqual(self.detector.detect_file(path), GameFormat.RENPY_RPA)

    def test_detect_rpa_32(self):
        path = self._create_rpa('test.rpa', b'RPA-3.2 0000000000000000 12345678\n')
        self.assertEqual(self.detector.detect_file(path), GameFormat.RENPY_RPA)

    def test_detect_unknown_file(self):
        path = self._create_rpa('test.bin', b'\x00\x00\x00\x00')
        self.assertEqual(self.detector.detect_file(path), GameFormat.UNKNOWN)

    def test_unity_old_bundle_not_false_positive_on_mp4(self):
        path = os.path.join(self.tmpdir, 'video.mp4')
        mp4_head = struct.pack('>I', 0x1C) + b'ftypisom' + b'\x00' * 64
        with open(path, 'wb') as f:
            f.write(mp4_head)
        self.assertEqual(self.detector.detect_file(path), GameFormat.UNKNOWN)

    def test_unity_old_bundle_requires_unity_marker(self):
        path = os.path.join(self.tmpdir, 'bundle.unity3d')
        head = b'\x00\x00\x00\x1c' + b'UnityRaw' + b'\x00' * 64
        with open(path, 'wb') as f:
            f.write(head)
        self.assertEqual(self.detector.detect_file(path), GameFormat.UNITY_ASSET)

    def test_detect_sfx_exe_as_generic_archive(self):
        payload_zip = os.path.join(self.tmpdir, 'payload.zip')
        with zipfile.ZipFile(payload_zip, 'w') as zf:
            zf.writestr('data/test.txt', 'hello')
        path = os.path.join(self.tmpdir, 'game.exe')
        with open(path, 'wb') as out, open(payload_zip, 'rb') as src:
            out.write(b'MZ' + b'\x00' * 128)
            out.write(src.read())
        self.assertEqual(self.detector.detect_file(path), GameFormat.GENERIC_7ZIP)

    def test_detect_unreal_pak_footer_magic(self):
        path = self._create_footer_pak('game.pak')
        self.assertEqual(self.detector.detect_file(path), GameFormat.UNREAL_PAK)

    def test_detect_folder_with_sfx_exe(self):
        payload_zip = os.path.join(self.tmpdir, 'payload2.zip')
        with zipfile.ZipFile(payload_zip, 'w') as zf:
            zf.writestr('data/test.txt', 'hello')
        path = os.path.join(self.tmpdir, 'game2.exe')
        with open(path, 'wb') as out, open(payload_zip, 'rb') as src:
            out.write(b'MZ' + b'\x00' * 128)
            out.write(src.read())
        info = self.detector.detect_folder(self.tmpdir)
        self.assertEqual(info.format, GameFormat.GENERIC_7ZIP)
        self.assertEqual(len(info.assets), 1)
        self.assertEqual(info.assets[0].path, path)

    def test_detect_folder_with_unreal_pak_footer_magic(self):
        pak_path = self._create_footer_pak(os.path.join('game', 'archive.pak'))
        info = self.detector.detect_folder(os.path.join(self.tmpdir, 'game'))
        self.assertEqual(info.format, GameFormat.UNREAL_PAK)
        self.assertEqual(len(info.assets), 1)
        self.assertEqual(info.assets[0].path, pak_path)

    def test_detect_nonexistent_file(self):
        self.assertEqual(
            self.detector.detect_file('Z:/nonexistent.rpa'),
            GameFormat.UNKNOWN
        )

    def test_detect_folder_with_rpa_files(self):
        rpa_path = self._create_rpa('archive.rpa', b'RPA-3.0 0000000000000000 12345678\n')
        info = self.detector.detect_folder(self.tmpdir)
        self.assertEqual(info.format, GameFormat.RENPY_RPA)
        self.assertEqual(len(info.assets), 1)
        self.assertEqual(info.assets[0].path, rpa_path)
        self.assertGreater(info.total_size, 0)

    def test_detect_empty_folder(self):
        info = self.detector.detect_folder(self.tmpdir)
        self.assertEqual(info.format, GameFormat.UNKNOWN)
        self.assertEqual(len(info.assets), 0)

    def test_detect_nonexistent_folder(self):
        info = self.detector.detect_folder('Z:/nonexistent')
        self.assertEqual(info.format, GameFormat.UNKNOWN)

    def test_detect_renpy_executable(self):
        with open(os.path.join(self.tmpdir, 'renpy.exe'), 'wb') as f:
            f.write(b'\x00' * 10)
        info = self.detector.detect_folder(self.tmpdir)
        self.assertEqual(info.format, GameFormat.RENPY_FOLDER)

    def test_collect_rpa_from_folder(self):
        self._create_rpa('a.rpa', b'RPA-3.0 0000000000000000 12345678\n')
        self._create_rpa('b.rpa', b'RPA-2.0 0000000000000000\n')
        self._create_rpa('c.bin', b'\x00\x00\x00\x00')  # Не .rpa
        files = self.detector.collect_rpa_files(self.tmpdir)
        self.assertEqual(len(files), 2)

    def test_collect_rpa_from_single_file(self):
        path = self._create_rpa('a.rpa', b'RPA-3.0 0000000000000000 12345678\n')
        files = self.detector.collect_rpa_files(path)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].path, path)


if __name__ == '__main__':
    unittest.main()
