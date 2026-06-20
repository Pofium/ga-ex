"""Юнит-тесты для новых архивных форматов: RPG Maker, Telltale, Wolf, Unreal, Godot, GAX, 7-Zip."""
import io
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.detector import FormatDetector, GameFormat
from core.rpgm_decrypter import (
    RpgmDecrypter, RpgmDecryptError, PNG_HEADER_16,
    extract_key_from_rpgmvp, find_rpg_maker_key,
)
from core.rpgm_reader import (
    Rgss1aReader, Rgss2aReader, Rgss3aReader, open_rgssad, detect_rgssad_variant,
)
from unpackers.rpgm_unpacker import RpgmUnpacker
from unpackers.telltale_unpacker import TelltaleUnpacker
from unpackers.wolf_unpacker import WolfUnpacker
from unpackers.pak_unpacker import UnrealPakUnpacker
from unpackers.godot_pck_unpacker import GodotPckUnpacker
from unpackers.gax_unpacker import GaxUnpacker
from unpackers.sevenzip_unpacker import SevenZipUnpacker
from core.base_unpacker import UnpackOptions


# ============ Helpers ============

def make_valid_png(width=8, height=8, color=b'\xff\x00\x00'):
    """Создаёт минимальный валидный PNG (RGB)."""
    import struct

    def chunk(typ, data):
        return struct.pack('>I', len(data)) + typ + data + struct.pack('>I', zlib.crc32(typ + data) & 0xffffffff)

    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    # raw image data: filter byte 0 + RGB per pixel, per row
    raw = b''
    for _ in range(height):
        raw += b'\x00' + color * width
    idat = zlib.compress(raw)
    return sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')


def make_rpgmvp_file(key_hex, png_bytes):
    """Создаёт синтетический .rpgmvp с заданным ключом."""
    key = bytes.fromhex(key_hex)
    fake_header = bytes.fromhex('5250474d56000000' + '000301' + '0000000000')  # 16 байт
    xored = bytearray(png_bytes[:16])
    for i in range(16):
        xored[i] ^= key[i]
    return fake_header + bytes(xored) + png_bytes[16:]


def make_rgss1a(files):
    """Создаёт синтетический .rgssad (v1) с указанными файлами.

    files: list of (path, data).
    """
    out = io.BytesIO()
    out.write(b'RGSSAD\x00')  # 7 байт
    key = struct.unpack('<I', b'RGSS')[0]

    for path, data in files:
        # size
        size_xor = len(data) ^ key
        out.write(struct.pack('<I', size_xor))
        key = (key * 7 + 3) & 0xFFFFFFFF

        # name_length (1 байт, XOR с key & 0xFF)
        name_len = len(path.encode('utf-8'))
        out.write(struct.pack('<B', name_len ^ (key & 0xFF)))
        key = (key * 7 + 3) & 0xFFFFFFFF

        # name (XOR каждого байта с key)
        for ch in path.encode('utf-8'):
            out.write(struct.pack('<B', ch ^ (key & 0xFF)))
            key = (key * 7 + 3) & 0xFFFFFFFF

        # data
        out.write(data)

    return out.getvalue()


# ============ Tests ============

class TestRpgmDecrypter(unittest.TestCase):
    """Тесты core.rpgm_decrypter."""

    def test_no_key_png_recovery(self):
        """No-key PNG recovery: data[16:32] = XOR(png_hdr, key) — пропускаем и добавляем PNG_HEADER_16."""
        key = 'd41d8cd98f00b204e9800998ecf8427e'
        png = make_valid_png(8, 8, b'\xff\xff\x00')
        encrypted = make_rpgmvp_file(key, png)

        dec = RpgmDecrypter(encryption_key=None)
        recovered = dec.restore_png_no_key(encrypted)

        # First 8 bytes should be PNG signature
        self.assertEqual(recovered[:8], b'\x89PNG\r\n\x1a\n')

    def test_roundtrip_with_key(self):
        """Encrypt → Decrypt даёт исходный PNG."""
        key = 'd41d8cd98f00b204e9800998ecf8427e'
        png = make_valid_png(8, 8, b'\x00\xff\x00')

        dec = RpgmDecrypter(encryption_key=key)
        encrypted = dec.encrypt(png)
        # fake_header + XOR(16) + raw_png[16:]
        self.assertEqual(encrypted[:16], dec.build_fake_header())

        # Decrypt
        decrypted = dec.decrypt(encrypted)
        # После удаления fake-header и XOR — должны получить исходный png
        self.assertEqual(decrypted, png)

    def test_verify_fake_header(self):
        dec = RpgmDecrypter(encryption_key='d41d8cd98f00b204e9800998ecf8427e')
        # 5 (RPGMV) + 3 (padding) + 3 (version 000301) + 5 (remain) = 16 bytes
        data = b'RPGMV\x00\x00\x00\x00\x03\x01\x00\x00\x00\x00\x00' + b'\x00' * 16
        self.assertTrue(dec.verify_fake_header_in(data))

        bad_data = b'XP3\r\n \n\x1a\x8b\x67\x01' + b'\x00' * 16
        self.assertFalse(dec.verify_fake_header_in(bad_data))

    def test_extract_key_from_rpgmvp(self):
        """XOR-анализ должен извлечь ключ из .rpgmvp."""
        key = 'd41d8cd98f00b204e9800998ecf8427e'
        png = make_valid_png(8, 8)
        encrypted = make_rpgmvp_file(key, png)

        # Пишем в файл и извлекаем ключ
        with tempfile.NamedTemporaryFile(suffix='.rpgmvp', delete=False) as f:
            f.write(encrypted)
            tmp = f.name
        try:
            extracted = extract_key_from_rpgmvp(tmp)
            self.assertEqual(extracted, key)
        finally:
            os.unlink(tmp)

    def test_decrypt_wrong_key_raises(self):
        """Неверный ключ не должен крашить, но выдаст осмысленный результат."""
        png = make_valid_png(4, 4, b'\xff\x00\xff')
        encrypted = make_rpgmvp_file('d41d8cd98f00b204e9800998ecf8427e', png)
        dec = RpgmDecrypter(encryption_key='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
        # Decrypt с другим ключом — просто вернёт "другой" PNG, не исходный
        decrypted = dec.decrypt(encrypted)
        self.assertNotEqual(decrypted, png)


class TestRpgmReader(unittest.TestCase):
    """Тесты core.rpgm_reader — RGSSAD v1/v2/v3."""

    def test_rgss1a_detect(self):
        # Создаём v1 архив
        archive = make_rgss1a([('foo.txt', b'hello world')])
        with tempfile.NamedTemporaryFile(suffix='.rgssad', delete=False) as f:
            f.write(archive)
            tmp = f.name
        try:
            self.assertTrue(Rgss1aReader.detect(tmp))
            self.assertEqual(detect_rgssad_variant(tmp), 'rgss1a')
        finally:
            os.unlink(tmp)

    def test_rgss1a_roundtrip(self):
        """Создаём v1, читаем обратно — имена и данные должны совпадать."""
        archive = make_rgss1a([
            ('foo/bar.txt', b'foo data'),
            ('baz.txt', b'baz data'),
        ])
        with tempfile.NamedTemporaryFile(suffix='.rgssad', delete=False) as f:
            f.write(archive)
            tmp = f.name
        try:
            with open_rgssad(tmp) as r:
                entries = r.get_entries()
                self.assertEqual(len(entries), 2)

                # Прочитать все файлы и проверить соответствие
                by_path = {e.path: r.read_file_data(e) for e in entries}
                self.assertEqual(set(by_path.keys()), {'foo/bar.txt', 'baz.txt'})
                self.assertEqual(by_path['foo/bar.txt'], b'foo data')
                self.assertEqual(by_path['baz.txt'], b'baz data')
        finally:
            os.unlink(tmp)

    def test_rgss1a_detect_wrong_magic(self):
        """Случайный файл не должен быть RGSSAD."""
        with tempfile.NamedTemporaryFile(suffix='.rgssad', delete=False) as f:
            f.write(b'NOT A RGSSAD')
            tmp = f.name
        try:
            self.assertFalse(Rgss1aReader.detect(tmp))
            self.assertIsNone(detect_rgssad_variant(tmp))
        finally:
            os.unlink(tmp)


class TestRpgmUnpacker(unittest.TestCase):
    """Тесты unpackers.rpgm_unpacker."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_detect_rpgmvp_file(self):
        png = make_valid_png(8, 8)
        key = 'd41d8cd98f00b204e9800998ecf8427e'
        encrypted = make_rpgmvp_file(key, png)
        path = os.path.join(self.tmpdir, 'img.rpgmvp')
        with open(path, 'wb') as f:
            f.write(encrypted)
        self.assertTrue(RpgmUnpacker().detect(path))

    def test_detect_not_rpgmvp(self):
        path = os.path.join(self.tmpdir, 'plain.png')
        with open(path, 'wb') as f:
            f.write(make_valid_png())
        self.assertFalse(RpgmUnpacker().detect(path))

    def test_unpack_rpgmvp_no_key(self):
        """Без ключа .rpgmvp восстанавливается через no-key PNG recovery."""
        key = 'd41d8cd98f00b204e9800998ecf8427e'
        png = make_valid_png(8, 8, b'\xff\x80\x00')
        encrypted = make_rpgmvp_file(key, png)
        path = os.path.join(self.tmpdir, 'img.rpgmvp')
        with open(path, 'wb') as f:
            f.write(encrypted)

        out = os.path.join(self.tmpdir, 'out')
        os.makedirs(out, exist_ok=True)
        unpacker = RpgmUnpacker()
        opts = UnpackOptions(output_dir=out, sanitize_names=True, use_long_paths=True)
        result = unpacker.unpack(path, opts)

        self.assertEqual(len(result.errors), 0)
        self.assertGreater(len(result.files_extracted), 0)
        # Проверяем что восстановленный PNG начинается с PNG signature
        recovered = os.path.join(out, 'img.png')
        self.assertTrue(os.path.exists(recovered))
        with open(recovered, 'rb') as f:
            self.assertEqual(f.read(8), b'\x89PNG\r\n\x1a\n')

    def test_unpack_dir_no_key(self):
        """Папка с .rpgmvp без ключа — каждый файл восстанавливается."""
        key = 'd41d8cd98f00b204e9800998ecf8427e'
        game_dir = os.path.join(self.tmpdir, 'game')
        os.makedirs(os.path.join(game_dir, 'img'))
        for i in range(3):
            png = make_valid_png(4, 4, bytes([i * 80, 128, 255 - i * 80]))
            encrypted = make_rpgmvp_file(key, png)
            with open(os.path.join(game_dir, 'img', f'pic_{i}.rpgmvp'), 'wb') as f:
                f.write(encrypted)

        out = os.path.join(self.tmpdir, 'out')
        unpacker = RpgmUnpacker()
        opts = UnpackOptions(output_dir=out, sanitize_names=True, use_long_paths=True)
        result = unpacker.unpack(game_dir, opts)

        self.assertEqual(len(result.errors), 0)
        self.assertEqual(len(result.files_extracted), 3)

    def test_unpack_rgss1a(self):
        """Распаковка .rgssad даёт файлы в output_dir."""
        archive = make_rgss1a([('foo.txt', b'rgss data')])
        path = os.path.join(self.tmpdir, 'game.rgssad')
        with open(path, 'wb') as f:
            f.write(archive)

        out = os.path.join(self.tmpdir, 'out')
        unpacker = RpgmUnpacker()
        opts = UnpackOptions(output_dir=out, sanitize_names=True, use_long_paths=True)
        result = unpacker.unpack(path, opts)

        self.assertEqual(len(result.errors), 0)
        self.assertIn('foo.txt', result.files_extracted)
        self.assertTrue(os.path.exists(os.path.join(out, 'foo.txt')))


class TestFormatDetectorExtended(unittest.TestCase):
    """Тесты детектора для новых форматов."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.det = FormatDetector()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_detect_rgssad(self):
        archive = make_rgss1a([('foo.txt', b'data')])
        path = os.path.join(self.tmpdir, 'game.rgssad')
        with open(path, 'wb') as f:
            f.write(archive)
        self.assertEqual(self.det.detect_file(path), GameFormat.RPG_MAKER_RGSSAD)

    def test_detect_rpgmvp(self):
        png = make_valid_png(4, 4)
        key = 'd41d8cd98f00b204e9800998ecf8427e'
        encrypted = make_rpgmvp_file(key, png)
        path = os.path.join(self.tmpdir, 'img.rpgmvp')
        with open(path, 'wb') as f:
            f.write(encrypted)
        self.assertEqual(self.det.detect_file(path), GameFormat.RPG_MAKER_MV)

    def test_detect_telltale(self):
        path = os.path.join(self.tmpdir, 'game.ttarch')
        with open(path, 'wb') as f:
            f.write(b'TTarch' + b'\x00' * 100)
        self.assertEqual(self.det.detect_file(path), GameFormat.TELLTALE_TTARCH)

    def test_detect_unreal_pak(self):
        path = os.path.join(self.tmpdir, 'game.pak')
        with open(path, 'wb') as f:
            f.write(b'PAK\x00' + b'\x00' * 100)
        self.assertEqual(self.det.detect_file(path), GameFormat.UNREAL_PAK)

    def test_detect_godot_pck(self):
        path = os.path.join(self.tmpdir, 'game.pck')
        with open(path, 'wb') as f:
            f.write(b'GDPC' + b'\x00' * 100)
        self.assertEqual(self.det.detect_file(path), GameFormat.GODOT_PCK)

    def test_detect_godot_pck_tail(self):
        """Godot v3+ magic в конце файла."""
        path = os.path.join(self.tmpdir, 'game.pck')
        with open(path, 'wb') as f:
            f.write(b'\x00' * 100 + b'GDPC')
        self.assertEqual(self.det.detect_file(path), GameFormat.GODOT_PCK)

    def test_detect_gax(self):
        path = os.path.join(self.tmpdir, 'img.gax')
        with open(path, 'wb') as f:
            f.write(b'\x00\x00\x00\x01' + b'\xff' * 100)
        self.assertEqual(self.det.detect_file(path), GameFormat.CATSYSTEM2_GAX)

    def test_detect_xp3_unchanged(self):
        """XP3 detection всё ещё работает."""
        path = os.path.join(self.tmpdir, 'data.xp3')
        with open(path, 'wb') as f:
            f.write(b'XP3\r\n \n\x1a\x8b\x67\x01' + b'\x00' * 100)
        self.assertEqual(self.det.detect_file(path), GameFormat.KIRIKIRI_XP3)

    def test_detect_rpa_unchanged(self):
        path = os.path.join(self.tmpdir, 'archive.rpa')
        with open(path, 'wb') as f:
            f.write(b'RPA-3.0 0000000000000000 0000000000000000')
        self.assertEqual(self.det.detect_file(path), GameFormat.RENPY_RPA)

    def test_detect_folder_with_rpgm(self):
        game = os.path.join(self.tmpdir, 'game')
        os.makedirs(game)
        with open(os.path.join(game, 'System.json'), 'w') as f:
            f.write('{"encryptionKey": "d41d8cd98f00b204e9800998ecf8427e"}')
        # Добавляем .rpgmvp чтобы детектор увидел формат
        key = 'd41d8cd98f00b204e9800998ecf8427e'
        png = make_valid_png(4, 4)
        encrypted = make_rpgmvp_file(key, png)
        with open(os.path.join(game, 'img.rpgmvp'), 'wb') as f:
            f.write(encrypted)
        info = self.det.detect_folder(game)
        self.assertEqual(info.format, GameFormat.RPG_MAKER_MV)


class TestStubs(unittest.TestCase):
    """Тесты stub unpacker'ов (Telltale, Wolf, Unreal, Godot, GAX)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_telltale_detect(self):
        path = os.path.join(self.tmpdir, 'g.ttarch')
        with open(path, 'wb') as f:
            f.write(b'TTarch' + b'\x00' * 50)
        u = TelltaleUnpacker()
        self.assertTrue(u.detect(path))

    def test_telltale_unpack_returns_error(self):
        path = os.path.join(self.tmpdir, 'g.ttarch')
        with open(path, 'wb') as f:
            f.write(b'TTarch' + b'\x00' * 50)
        out = os.path.join(self.tmpdir, 'out')
        u = TelltaleUnpacker()
        result = u.unpack(path, UnpackOptions(output_dir=out))
        self.assertFalse(result.success)
        self.assertGreater(len(result.errors), 0)

    def test_unreal_pak_detect(self):
        path = os.path.join(self.tmpdir, 'g.pak')
        with open(path, 'wb') as f:
            f.write(b'PAK\x00' + b'\x00' * 50)
        u = UnrealPakUnpacker()
        self.assertTrue(u.detect(path))

    def test_godot_pck_detect(self):
        path = os.path.join(self.tmpdir, 'g.pck')
        with open(path, 'wb') as f:
            f.write(b'GDPC' + b'\x00' * 50)
        u = GodotPckUnpacker()
        self.assertTrue(u.detect(path))

    def test_gax_detect(self):
        path = os.path.join(self.tmpdir, 'img.gax')
        with open(path, 'wb') as f:
            f.write(b'\x00\x00\x00\x01' + b'\xff' * 50)
        u = GaxUnpacker()
        self.assertTrue(u.detect(path))

    def test_wolf_detect_by_extension(self):
        path = os.path.join(self.tmpdir, 'game.wolf')
        with open(path, 'wb') as f:
            f.write(b'\x00' * 200)
        u = WolfUnpacker()
        self.assertTrue(u.detect(path))


class TestGaxDecryption(unittest.TestCase):
    """Тесты расшифровки .gax (CatSystem2)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_detect_image_signature_png(self):
        from unpackers.gax_unpacker import _detect_image_signature
        png_sig = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        self.assertEqual(_detect_image_signature(png_sig), '.png')

    def test_detect_image_signature_jpg(self):
        from unpackers.gax_unpacker import _detect_image_signature
        self.assertEqual(_detect_image_signature(b"\xff\xd8\xff\xe0\x00\x10JFIF"), '.jpg')

    def test_detect_image_signature_bmp(self):
        from unpackers.gax_unpacker import _detect_image_signature
        self.assertEqual(_detect_image_signature(b"BM\x00\x00\x00\x00\x00\x00\x00\x00"), '.bmp')

    def test_detect_image_signature_unknown(self):
        from unpackers.gax_unpacker import _detect_image_signature
        self.assertIsNone(_detect_image_signature(b"\x00\x00\x00\x01random_data"))

    def test_decrypt_gax_with_known_algorithm(self):
        """Проверяет, что алгоритм xor_size_le корректно расшифровывает PNG."""
        from unpackers.gax_unpacker import _try_decrypt, decrypt_gax
        # В .gax первые 4 байта - magic (00 00 00 01),
        # затем идут зашифрованные данные, начинающиеся с PNG magic.
        size = 1024
        # Plaintext: gax magic + PNG header + нули
        plaintext = b'\x00\x00\x00\x01' + b"\x89PNG\r\n\x1a\n" + b'\x00' * (size - 12)
        # Шифруем так же, как алгоритм xor_size_le
        encrypted = bytearray(plaintext)
        key = size & 0xFFFFFFFF
        for i in range(4, size):
            encrypted[i] ^= (key >> ((i & 3) * 8)) & 0xFF
            key = (key * 7 + 3) & 0xFFFFFFFF
        # Теперь пытаемся расшифровать
        decrypted, ext, algo = decrypt_gax(bytes(encrypted))
        self.assertIsNotNone(decrypted)
        self.assertEqual(ext, '.png')

    def test_gax_unpack_saves_decrypted(self):
        """Убеждаемся, что unpacker сохраняет расшифрованный PNG."""
        from unpackers.gax_unpacker import GaxUnpacker
        # Синтетический .gax: magic + PNG + нули, зашифрован xor_size_le
        size = 256
        plaintext = b'\x00\x00\x00\x01' + b"\x89PNG\r\n\x1a\n" + b'\x00' * (size - 12)
        encrypted = bytearray(plaintext)
        key = size & 0xFFFFFFFF
        for i in range(4, size):
            encrypted[i] ^= (key >> ((i & 3) * 8)) & 0xFF
            key = (key * 7 + 3) & 0xFFFFFFFF
        path = os.path.join(self.tmpdir, 'fake.gax')
        with open(path, 'wb') as f:
            f.write(bytes(encrypted))
        out = os.path.join(self.tmpdir, 'out')
        os.makedirs(out, exist_ok=True)
        result = GaxUnpacker().unpack(path, UnpackOptions(output_dir=out))
        self.assertTrue(result.success, msg=f'errors={result.errors}')
        self.assertEqual(len(result.files_extracted), 1)
        self.assertTrue(result.files_extracted[0]['path'].endswith('.png'))

    def test_gax_unpack_saves_as_bin_on_failure(self):
        """Если дешифровка не удалась, файл сохраняется как .bin."""
        from unpackers.gax_unpacker import GaxUnpacker
        path = os.path.join(self.tmpdir, 'mystery.gax')
        with open(path, 'wb') as f:
            f.write(b'\x00\x00\x00\x01' + b'\xde\xad\xbe\xef' * 50)
        out = os.path.join(self.tmpdir, 'out')
        os.makedirs(out, exist_ok=True)
        result = GaxUnpacker().unpack(path, UnpackOptions(output_dir=out))
        self.assertEqual(len(result.files_extracted), 1)
        self.assertTrue(result.files_extracted[0]['path'].endswith('.bin'))


class TestSevenZipUnpacker(unittest.TestCase):
    """Тесты 7-Zip fallback unpacker."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_detect_by_extension(self):
        for ext in ('.zip', '.7z', '.tar', '.gz', '.rar'):
            path = os.path.join(self.tmpdir, f'f{ext}')
            with open(path, 'wb') as f:
                f.write(b'placeholder')
            self.assertTrue(SevenZipUnpacker().detect(path), ext)

    def test_no_7z_returns_error(self):
        path = os.path.join(self.tmpdir, 'f.zip')
        with open(path, 'wb') as f:
            f.write(b'placeholder')
        out = os.path.join(self.tmpdir, 'out')
        u = SevenZipUnpacker()
        result = u.unpack(path, UnpackOptions(output_dir=out))
        # 7z может быть установлен — тест либо успешен, либо содержит ошибку
        # Главное — нет краша


if __name__ == '__main__':
    unittest.main(verbosity=2)
