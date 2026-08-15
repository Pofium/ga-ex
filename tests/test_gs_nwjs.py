"""Unit-тесты: GS-NWJS движок (House of Maids и др.) — детектор и распаковщик.

GS-движок на NW.js шифрует ресурсы XOR с фиксированным 5-байтным ключом
``0A 2B 36 6F 0B``. Тесты покрывают:
  - детектор отдельного зашифрованного файла (PNG/JPG/OGG/WAV/WOFF);
  - детектор папки игры по маркеру в data/ENGINE.js + окружению NW.js;
  - отсутствие ложных срабатываний на обычных (незашифрованных) файлах;
  - распаковщик: дешифровка отдельного файла и целой папки игры.
"""
import os
import sys
import struct
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.detector import FormatDetector, GameFormat
from core.base_unpacker import UnpackOptions
from unpackers.gs_nwjs_unpacker import GsNwjsUnpacker


KEY = FormatDetector.GS_NWJS_KEY


def _xor(data: bytes) -> bytes:
    return bytes(data[i] ^ KEY[i % len(KEY)] for i in range(len(data)))


def _make_png(width: int = 2, height: int = 2) -> bytes:
    """Минимальный валидный PNG (RGB, один IDAT)."""
    sig = b'\x89PNG\r\n\x1a\n'

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack('>I', len(payload)) + tag + payload
                + struct.pack('>I', zlib.crc32(tag + payload) & 0xffffffff))

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    # Каждая строка начинается с байта фильтра (0), затем width*3 байт RGB.
    raw = b''
    for _y in range(height):
        raw += b'\x00' + b'\xff\x00\x00' * width
    idat = zlib.compress(raw)
    return sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')


class TestGsNwjsDetector(unittest.TestCase):
    def setUp(self):
        self.detector = FormatDetector()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, rel: str, data: bytes) -> str:
        path = os.path.join(self.tmpdir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)
        return path

    # ---- отдельные файлы ----

    def test_detect_encrypted_png(self):
        path = self._write('pic.png', _xor(_make_png()))
        self.assertEqual(self.detector.detect_file(path), GameFormat.GS_NWJS)

    def test_detect_encrypted_jpg(self):
        path = self._write('img.jpg', _xor(b'\xff\xd8\xff\xe0' + b'JFIF' + b'\x00' * 50))
        self.assertEqual(self.detector.detect_file(path), GameFormat.GS_NWJS)

    def test_detect_encrypted_ogg(self):
        path = self._write('song.ogg', _xor(b'OggS' + b'\x00' * 60))
        self.assertEqual(self.detector.detect_file(path), GameFormat.GS_NWJS)

    def test_detect_encrypted_wav(self):
        path = self._write('sfx.wav', _xor(b'RIFF' + b'\x00' * 60))
        self.assertEqual(self.detector.detect_file(path), GameFormat.GS_NWJS)

    def test_detect_encrypted_woff(self):
        path = self._write('font.woff', _xor(b'wOFF' + b'\x00' * 60))
        self.assertEqual(self.detector.detect_file(path), GameFormat.GS_NWJS)

    def test_detect_encrypted_webm(self):
        path = self._write('clip.webm', _xor(b'\x1a\x45\xdf\xa3' + b'\x00' * 60))
        self.assertEqual(self.detector.detect_file(path), GameFormat.GS_NWJS)

    def test_normal_png_not_detected_as_gs(self):
        """Обычный незашифрованный PNG не должен детектироваться как GS."""
        path = self._write('normal.png', _make_png())
        self.assertNotEqual(self.detector.detect_file(path), GameFormat.GS_NWJS)

    def test_random_data_not_detected(self):
        path = self._write('garbage.png', os.urandom(128))
        self.assertNotEqual(self.detector.detect_file(path), GameFormat.GS_NWJS)

    # ---- папка игры ----

    def _make_game_folder(self) -> str:
        """Создаёт минимальную GS-игру: ENGINE.js с маркером, nw.dll, ресурсы."""
        engine = (
            b'window.gs={},GS.DataPreparer=function(){'
            b'this.needsPreparation=!0};'
            b'GS.DataPreparer.generateKey=function(){return [10,43,54,111,11]};'
        )
        self._write('data/ENGINE.js', engine)
        # Маркер NW.js окружения
        self._write('nw.dll', b'MZ' + b'\x00' * 100)
        self._write('package.json', b'{"name":"test","main":"index.html"}')
        # Зашифрованные ресурсы
        self._write('resources/Graphics/bg.png', _xor(_make_png(4, 4)))
        self._write('resources/Audio/music.ogg', _xor(b'OggS' + b'\x00' * 40))
        # Открытый движковый скрипт (НЕ должен шифроваться/тащиться как ассет)
        self._write('data/lib/boot.js', b'function boot(){}')
        return self.tmpdir

    def test_is_gs_game_folder(self):
        root = self._make_game_folder()
        self.assertTrue(FormatDetector.is_gs_nwjs_game_folder(root))

    def test_detect_folder_returns_gs(self):
        root = self._make_game_folder()
        info = self.detector.detect_folder(root)
        self.assertEqual(info.format, GameFormat.GS_NWJS)
        # Один ассет = корень игры
        self.assertEqual(len(info.assets), 1)
        self.assertEqual(info.assets[0].format, GameFormat.GS_NWJS)
        self.assertGreater(info.total_size, 0)

    def test_empty_folder_not_gs(self):
        info = self.detector.detect_folder(self.tmpdir)
        self.assertEqual(info.format, GameFormat.UNKNOWN)


class TestGsNwjsUnpacker(unittest.TestCase):
    def setUp(self):
        self.unpacker = GsNwjsUnpacker()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, rel: str, data: bytes) -> str:
        path = os.path.join(self.tmpdir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)
        return path

    def test_unpack_single_file(self):
        original = _make_png(3, 3)
        src = self._write('src/pic.png', _xor(original))
        out = os.path.join(self.tmpdir, 'out')
        result = self.unpacker.unpack(src, UnpackOptions(output_dir=out))

        self.assertTrue(result.success, msg=f'errors: {result.errors}')
        self.assertEqual(len(result.files_extracted), 1)
        dec_path = os.path.join(out, 'pic.png')
        self.assertTrue(os.path.isfile(dec_path))
        with open(dec_path, 'rb') as f:
            dec = f.read()
        self.assertEqual(dec, original)
        self.assertTrue(dec.startswith(b'\x89PNG'))

    def test_unpack_folder(self):
        """Дешифрует медиа и скрипты, сохраняя структуру каталогов."""
        png = _make_png(2, 2)
        # Структура GS-игры
        self._write('data/ENGINE.js', b'GS.DataPreparer=function(){};needsPreparation=1;')
        self._write('nw.dll', b'MZ' + b'\x00' * 50)
        self._write('resources/Graphics/bg.png', _xor(png))
        self._write('resources/Audio/m.ogg', _xor(b'OggS' + b'\x00' * 30))
        # Зашифрованный скрипт (после XOR — валидный JS)
        self._write('data/abc.json.js', _xor(b"GS.dataCache['abc']={};"))
        # Открытый движковый скрипт — НЕ должен дешифроваться/копироваться
        lib_path = os.path.join(self.tmpdir, 'data/lib/boot.js')
        os.makedirs(os.path.dirname(lib_path), exist_ok=True)
        with open(lib_path, 'wb') as f:
            f.write(b'function boot(){}')

        out = os.path.join(self.tmpdir, 'out')
        result = self.unpacker.unpack(self.tmpdir, UnpackOptions(output_dir=out))

        self.assertTrue(result.success, msg=f'errors: {result.errors}')
        extracted = set(result.files_extracted)
        # Медиа дешифрованы
        self.assertIn('resources/Graphics/bg.png', extracted)
        self.assertIn('resources/Audio/m.ogg', extracted)
        # Скрипт дешифрован
        self.assertIn('data/abc.json.js', extracted)
        # Движковый lib-скрипт НЕ должен попасть в вывод
        self.assertNotIn('data/lib/boot.js', extracted)

        # Проверяем корректность дешифровки PNG
        with open(os.path.join(out, 'resources/Graphics/bg.png'), 'rb') as f:
            dec = f.read()
        self.assertEqual(dec, png)
        self.assertTrue(dec.startswith(b'\x89PNG'))

        # Проверяем корректность дешифровки скрипта
        with open(os.path.join(out, 'data/abc.json.js'), 'rb') as f:
            dec_js = f.read()
        self.assertEqual(dec_js, b"GS.dataCache['abc']={};")

    def test_unpack_path_traversal_rejected(self):
        """Имя с .. не должно писать вне output_dir."""
        # Имя файла с traversal-последовательностью
        path = os.path.join(self.tmpdir, '..', 'evil.png')
        # Создаём валидный зашифрованный файл с опасным именем внутри tmpdir
        evil = os.path.join(self.tmpdir, 'sub', '..\\evil.png')
        os.makedirs(os.path.join(self.tmpdir, 'sub'), exist_ok=True)
        with open(os.path.join(self.tmpdir, 'sub', 'evil.png'), 'wb') as f:
            f.write(_xor(_make_png()))
        src = os.path.join(self.tmpdir, 'sub', 'evil.png')
        out = os.path.join(self.tmpdir, 'out')
        result = self.unpacker.unpack(src, UnpackOptions(output_dir=out))
        self.assertTrue(result.success)
        self.assertTrue(os.path.isfile(os.path.join(out, 'evil.png')))
        # Чистим возможный мусор
        if os.path.exists(path):
            os.remove(path)

    def test_detect_file_and_folder(self):
        self._write('nw.dll', b'MZ' + b'\x00' * 40)
        self._write('data/ENGINE.js', b'GS.DataPreparer=function(){};needsPreparation=1;')
        self.assertTrue(self.unpacker.detect(self.tmpdir))
        enc = self._write('pic.png', _xor(_make_png()))
        self.assertTrue(self.unpacker.detect(enc))


if __name__ == '__main__':
    unittest.main()
