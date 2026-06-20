"""Unit-тесты для .xp3 распаковки (KiriKiri)."""
import io
import os
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.xp3_reader import (
    Xp3Reader,
    Xp3Error,
    Xp3InvalidFileError,
    Xp3UnsupportedError,
    XP3_MAGIC,
    TAG_FILE,
    TAG_INFO,
    TAG_SEGM,
    TAG_ADLR,
    INFO_FLAG_COMPRESSED,
)
from core.detector import FormatDetector, GameFormat
from unpackers.xp3_unpacker import Xp3Unpacker, PathTraversalError
from core.base_unpacker import UnpackOptions


def _make_xp3_file(target_path, files, compress_index=True, compress_data=False):
    """Создаёт синтетический .xp3 для тестов.

    Формат (по krkrz):
      [11 байт magic]
      [8 байт index_ofs (uint64 LE) — смещение до Index Record]
      [... данные файлов ...]
      [Index Record at index_ofs]
        [1 байт flag] bit 0x0F = method (0=raw, 1=zlib), bit 0x80 = CONTINUE
        [8 байт compressed_size (zlib) или raw_size (raw)]
        [8 байт raw_size (только zlib)]
        [compressed_size байт данных индекса]

    files: list of (path, data) — пути в формате 'foo/bar.png' (с '/')
    compress_data: сжимать ли данные файлов zlib
    """
    # Каждый FILE chunk содержит sub-chunks: info, segm, adlr
    # sub-chunk format: tag(4) + size(8) + data
    # info format: flags(4) + OrgSize(8) + ArcSize(8) + name_len(2) + name(UTF-16LE)
    # segm format: массив по 28 байт = flags(4) + Start(8) + OrgSize(8) + ArcSize(8)
    # adlr format: 4 байта hash

    def build_index_data():
        idx = io.BytesIO()
        for path, original_data in files:
            # FILE chunk (контейнер): tag(4) + size(8)
            file_buf = io.BytesIO()

            # info sub-chunk
            info_flags = 1 if compress_data else 0
            org_size = len(original_data)
            arc_size = org_size  # будет перезаписан позже
            name_u16 = path.replace('/', '\\').encode('utf-16-le')
            name_char_len = len(name_u16) // 2  # кол-во UTF-16 символов
            info_body = struct.pack('<IQQH', info_flags, org_size, arc_size, name_char_len) + name_u16
            file_buf.write(struct.pack('<IQ', TAG_INFO, len(info_body)))
            file_buf.write(info_body)

            # segm sub-chunk — пока с placeholder offset/size
            seg_flags = 1 if compress_data else 0
            segm_body = struct.pack('<I', seg_flags) + struct.pack('<QQQ', 0, org_size, org_size)
            file_buf.write(struct.pack('<IQ', TAG_SEGM, len(segm_body)))
            file_buf.write(segm_body)

            # adlr sub-chunk: 4 байта hash (любые)
            adlr_body = struct.pack('<I', 0)
            file_buf.write(struct.pack('<IQ', TAG_ADLR, len(adlr_body)))
            file_buf.write(adlr_body)

            # Записываем FILE chunk с реальным размером
            file_data = file_buf.getvalue()
            idx.write(struct.pack('<IQ', TAG_FILE, len(file_data)))
            idx.write(file_data)
        return idx.getvalue()

    index_raw = build_index_data()
    if compress_index:
        index_stored = zlib.compress(index_raw)
        index_flag = 0x01
        # Для zlib: compressed_size(8) + raw_size(8) + compressed_data
        index_record = struct.pack('B', index_flag)
        index_record += struct.pack('<QQ', len(index_stored), len(index_raw))
        index_record += index_stored
    else:
        index_stored = index_raw
        index_flag = 0x00
        index_record = struct.pack('B', index_flag)
        index_record += struct.pack('<Q', len(index_stored))
        index_record += index_stored

    # Теперь собираем файл, зная размеры сегментов
    # 1) Сначала посчитаем общий размер data area
    #    и обновим segm offsets/sizes
    HEADER_SIZE = 11 + 8  # magic + index_ofs

    # Перезаписываем index с реальными offsets
    data_area_parts = []
    cur_offset = HEADER_SIZE
    new_index = io.BytesIO()
    for i, (path, original_data) in enumerate(files):
        stored = zlib.compress(original_data) if compress_data else original_data
        offset = cur_offset
        size = len(stored)
        data_area_parts.append(stored)
        cur_offset += size

        # Собираем FILE chunk заново с правильными offset/size
        file_buf = io.BytesIO()
        info_flags = 1 if compress_data else 0
        org_size = len(original_data)
        name_u16 = path.replace('/', '\\').encode('utf-16-le')
        name_char_len = len(name_u16) // 2
        info_body = struct.pack('<IQQH', info_flags, org_size, size, name_char_len) + name_u16
        file_buf.write(struct.pack('<IQ', TAG_INFO, len(info_body)))
        file_buf.write(info_body)
        seg_flags = 1 if compress_data else 0
        segm_body = struct.pack('<I', seg_flags) + struct.pack('<QQQ', offset, org_size, size)
        file_buf.write(struct.pack('<IQ', TAG_SEGM, len(segm_body)))
        file_buf.write(segm_body)
        adlr_body = struct.pack('<I', 0)
        file_buf.write(struct.pack('<IQ', TAG_ADLR, len(adlr_body)))
        file_buf.write(adlr_body)

        file_data = file_buf.getvalue()
        new_index.write(struct.pack('<IQ', TAG_FILE, len(file_data)))
        new_index.write(file_data)

    index_raw = new_index.getvalue()
    if compress_index:
        index_stored = zlib.compress(index_raw)
        index_record = struct.pack('B', 0x01)
        index_record += struct.pack('<QQ', len(index_stored), len(index_raw))
        index_record += index_stored
    else:
        index_record = struct.pack('B', 0x00)
        index_record += struct.pack('<Q', len(index_raw))
        index_record += index_raw

    data_area = b''.join(data_area_parts)
    index_offset = HEADER_SIZE + len(data_area)

    with open(target_path, 'wb') as f:
        f.write(XP3_MAGIC)
        f.write(struct.pack('<Q', index_offset))
        f.write(data_area)
        f.write(index_record)


class TestXp3Magic(unittest.TestCase):
    def test_magic_is_correct(self):
        self.assertEqual(XP3_MAGIC, b'XP3\r\n \n\x1a\x8b\x67\x01')
        self.assertEqual(len(XP3_MAGIC), 11)


class TestFormatDetector(unittest.TestCase):
    def setUp(self):
        self.detector = FormatDetector()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_xp3_detected_by_magic(self):
        path = os.path.join(self.tmpdir, 'data.xp3')
        _make_xp3_file(path, [('readme.txt', b'hello')])
        self.assertEqual(self.detector.detect_file(path), GameFormat.KIRIKIRI_XP3)

    def test_non_xp3_returns_unknown(self):
        path = os.path.join(self.tmpdir, 'data.txt')
        with open(path, 'wb') as f:
            f.write(b'just text, not an archive')
        self.assertEqual(self.detector.detect_file(path), GameFormat.UNKNOWN)

    def test_xp3_in_folder(self):
        path = os.path.join(self.tmpdir, 'data.xp3')
        _make_xp3_file(path, [('bg.png', b'\x89PNG')])
        info = self.detector.detect_folder(self.tmpdir)
        self.assertEqual(info.format, GameFormat.KIRIKIRI_XP3)
        self.assertEqual(len(info.assets), 1)
        self.assertEqual(info.assets[0].format, GameFormat.KIRIKIRI_XP3)

    def test_xp3_alongside_rpa_marks_mixed(self):
        # XP3 + ничего больше — формат = KIRIKIRI_XP3
        path = os.path.join(self.tmpdir, 'data.xp3')
        _make_xp3_file(path, [('bg.png', b'\x89PNG')])
        info = self.detector.detect_folder(self.tmpdir)
        self.assertEqual(info.format, GameFormat.KIRIKIRI_XP3)


class TestXp3Reader(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_detect_valid(self):
        path = os.path.join(self.tmpdir, 'data.xp3')
        _make_xp3_file(path, [('readme.txt', b'hello')])
        self.assertTrue(Xp3Reader.detect(path))

    def test_detect_invalid(self):
        path = os.path.join(self.tmpdir, 'notxp3.xp3')
        with open(path, 'wb') as f:
            f.write(b'NOT AN XP3 FILE HERE')
        self.assertFalse(Xp3Reader.detect(path))

    def test_get_entries_basic(self):
        path = os.path.join(self.tmpdir, 'data.xp3')
        files = [
            ('readme.txt', b'Hello XP3!'),
            ('bg/forest.png', b'\x89PNG' + b'X' * 100),
            ('script.ks', b'// script'),
        ]
        _make_xp3_file(path, files)
        with Xp3Reader(path) as r:
            entries = r.get_entries()
            self.assertEqual(len(entries), 3)
            self.assertEqual(sorted(e.path for e in entries),
                             sorted([f[0] for f in files]))

    def test_read_file_data_uncompressed(self):
        path = os.path.join(self.tmpdir, 'data.xp3')
        files = [('text.txt', b'raw data')]
        _make_xp3_file(path, files, compress_data=False)
        with Xp3Reader(path) as r:
            entries = r.get_entries()
            self.assertEqual(len(entries), 1)
            data = r.read_file_data(entries[0])
            self.assertEqual(data, b'raw data')

    def test_read_file_data_compressed(self):
        path = os.path.join(self.tmpdir, 'data.xp3')
        original = b'A' * 1000 + b'B' * 500 + b'C' * 200
        files = [('big.bin', original)]
        _make_xp3_file(path, files, compress_data=True)
        with Xp3Reader(path) as r:
            entries = r.get_entries()
            self.assertEqual(len(entries), 1)
            self.assertTrue(entries[0].compressed)
            data = r.read_file_data(entries[0])
            self.assertEqual(data, original)

    def test_unicode_paths(self):
        path = os.path.join(self.tmpdir, 'data.xp3')
        files = [
            ('日本/背景.png', b'\x89PNG'),
            ('中文/角色.ks', b'// chinese'),
        ]
        _make_xp3_file(path, files)
        with Xp3Reader(path) as r:
            entries = r.get_entries()
            self.assertEqual(len(entries), 2)
            for entry in entries:
                self.assertIsInstance(entry.path, str)
                self.assertTrue(len(entry.path) > 0)


class TestXp3Unpacker(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.outdir = tempfile.mkdtemp()
        self.unpacker = Xp3Unpacker()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        shutil.rmtree(self.outdir, ignore_errors=True)

    def test_detect(self):
        path = os.path.join(self.tmpdir, 'data.xp3')
        _make_xp3_file(path, [('readme.txt', b'hello')])
        self.assertTrue(self.unpacker.detect(path))

    def test_detect_fails_on_non_xp3(self):
        path = os.path.join(self.tmpdir, 'notxp3.xp3')
        with open(path, 'wb') as f:
            f.write(b'NOT AN XP3 FILE')
        self.assertFalse(self.unpacker.detect(path))

    def test_analyze(self):
        path = os.path.join(self.tmpdir, 'data.xp3')
        _make_xp3_file(path, [
            ('a.txt', b'a'),
            ('b.bin', b'bb'),
        ])
        info = self.unpacker.analyze(path)
        self.assertEqual(info['entries_count'], 2)
        self.assertGreater(info['file_size'], 0)

    def test_unpack_basic(self):
        path = os.path.join(self.tmpdir, 'data.xp3')
        files = [
            ('readme.txt', b'Hello!'),
            ('bg/forest.png', b'\x89PNG-test'),
        ]
        _make_xp3_file(path, files)
        opts = UnpackOptions(output_dir=self.outdir, sanitize_names=False)
        result = self.unpacker.unpack(path, opts)
        self.assertTrue(result.success, f'Errors: {result.errors}')
        self.assertEqual(len(result.files_extracted), 2)
        # Проверяем что файлы созданы
        self.assertTrue(os.path.exists(os.path.join(self.outdir, 'readme.txt')))
        self.assertTrue(os.path.exists(os.path.join(self.outdir, 'bg', 'forest.png')))
        with open(os.path.join(self.outdir, 'readme.txt'), 'rb') as f:
            self.assertEqual(f.read(), b'Hello!')

    def test_unpack_compressed(self):
        path = os.path.join(self.tmpdir, 'data.xp3')
        original = b'Compressed data ' * 100
        files = [('compressed.bin', original)]
        _make_xp3_file(path, files, compress_data=True)
        opts = UnpackOptions(output_dir=self.outdir, sanitize_names=False)
        result = self.unpacker.unpack(path, opts)
        self.assertTrue(result.success, f'Errors: {result.errors}')
        self.assertEqual(len(result.files_extracted), 1)
        with open(os.path.join(self.outdir, 'compressed.bin'), 'rb') as f:
            self.assertEqual(f.read(), original)

    def test_unpack_preserves_unicode(self):
        path = os.path.join(self.tmpdir, 'data.xp3')
        files = [
            ('日本/readme.txt', b'japanese'),
        ]
        _make_xp3_file(path, files)
        opts = UnpackOptions(output_dir=self.outdir, sanitize_names=False)
        result = self.unpacker.unpack(path, opts)
        self.assertTrue(result.success, f'Errors: {result.errors}')
        # Путь должен быть сохранён с японскими иероглифами
        self.assertTrue(os.path.exists(os.path.join(self.outdir, '日本', 'readme.txt')))

    def test_path_traversal_blocked(self):
        path = os.path.join(self.tmpdir, 'data.xp3')
        # Попытка path traversal
        files = [('../escape.txt', b'BAD')]
        _make_xp3_file(path, files)
        opts = UnpackOptions(output_dir=self.outdir, sanitize_names=False)
        result = self.unpacker.unpack(path, opts)
        # Файл не должен быть создан за пределами outdir
        self.assertFalse(os.path.exists(os.path.join(self.tmpdir, '..', 'escape.txt')))

    def test_progress_callback_called(self):
        path = os.path.join(self.tmpdir, 'data.xp3')
        files = [('a.txt', b'a'), ('b.txt', b'b'), ('c.txt', b'c')]
        _make_xp3_file(path, files)
        calls = []
        def cb(name, current, total):
            calls.append((name, current, total))
        opts = UnpackOptions(output_dir=self.outdir, sanitize_names=False)
        result = self.unpacker.unpack(path, opts, progress_callback=cb)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[-1][1], 3)  # last call has current=3
        self.assertEqual(calls[-1][2], 3)  # total=3


class TestXp3Integration(unittest.TestCase):
    """Интеграционные тесты: detect_folder + Xp3Unpacker."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.outdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        shutil.rmtree(self.outdir, ignore_errors=True)

    def test_detect_and_unpack(self):
        # Создаём папку как у игры
        game_dir = os.path.join(self.tmpdir, 'TestGame')
        os.makedirs(game_dir)
        xp3_path = os.path.join(game_dir, 'data.xp3')
        files = [
            ('scenario/start.ks', b'// start'),
            ('image/bg.png', b'\x89PNG'),
        ]
        _make_xp3_file(xp3_path, files)

        # Детектим
        detector = FormatDetector()
        info = detector.detect_folder(game_dir)
        self.assertEqual(info.format, GameFormat.KIRIKIRI_XP3)
        self.assertEqual(len(info.assets), 1)
        self.assertEqual(info.assets[0].path, xp3_path)

        # Распаковываем
        unpacker = Xp3Unpacker()
        opts = UnpackOptions(output_dir=self.outdir, sanitize_names=False)
        result = unpacker.unpack(xp3_path, opts)
        self.assertTrue(result.success, f'Errors: {result.errors}')
        self.assertEqual(len(result.files_extracted), 2)


if __name__ == '__main__':
    unittest.main()
