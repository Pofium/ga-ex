"""Unit-тесты: парсинг заголовка RPA-3.0."""
import os
import sys
import struct
import zlib
import pickle
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rpa_reader import RpaReader, RpaEntry
from core.errors import InvalidHeaderError, InvalidIndexError


def _create_test_rpa(tmpdir: str, version: str = '3.0', key: int = 0x42424242,
                     files: dict = None) -> str:
    """Создаёт минимальный тестовый .rpa файл.
    ВНИМАНИЕ: индекс ВСЕГДА хранится как zlib(pickle(...)) БЕЗ XOR.
    XOR с ключом применяется только к offset и length в payload.
    """
    if files is None:
        files = {'test/hello.txt': b'Hello, world!', 'test/data.bin': b'\\x00\\x01\\x02'}

    filepath = os.path.join(tmpdir, f'test_{version.replace(".", "")}.rpa')

    # Сначала строим индекс с ПРАВИЛЬНЫМИ (раскодированными) offsets/lengths.
    # После того как узнаем реальные offsets, пересоберём с зашифрованными.
    temp_index = {}
    for path in files:
        if version == '2.0':
            temp_index[path] = [(0, len(files[path]), 0)]
        else:
            temp_index[path] = [(0 ^ key, len(files[path]) ^ key, 0)]

    index_pickled = pickle.dumps(temp_index, pickle.HIGHEST_PROTOCOL)
    # ВНИМАНИЕ: zlib НЕ XOR-ится — это правильное поведение для RPA-3.0
    index_data = zlib.compress(index_pickled)

    # Записываем файл: header | data | index
    with open(filepath, 'wb') as f:
        # Header placeholder
        if version == '2.0':
            f.write(f'RPA-2.0 {0:016x}\n'.encode())
        elif version == '3.0':
            f.write(f'RPA-3.0 {0:016x} {key:x}\n'.encode())
        else:
            f.write(f'RPA-3.2 {0:016x} 00000000 {key:x}\n'.encode())

        data_start = f.tell()
        positions = {}
        for path, data in files.items():
            positions[path] = (f.tell(), len(data))
            f.write(data)

        index_offset = f.tell()
        f.write(index_data)

    # Теперь у нас есть реальные offsets — пересоберём индекс с зашифрованными
    # (offset, length) и перезапишем
    raw_index = {}
    for path, (offset, length) in positions.items():
        if version == '2.0':
            raw_index[path] = [(offset, length, 0)]
        else:
            raw_index[path] = [(offset ^ key, length ^ key, 0)]

    index_pickled = pickle.dumps(raw_index, pickle.HIGHEST_PROTOCOL)
    index_data = zlib.compress(index_pickled)

    # Перезаписываем header с правильным index_offset и сам индекс
    with open(filepath, 'r+b') as f:
        if version == '2.0':
            f.write(f'RPA-2.0 {index_offset:016x}\n'.encode())
        elif version == '3.0':
            f.write(f'RPA-3.0 {index_offset:016x} {key:x}\n'.encode())
        else:
            f.write(f'RPA-3.2 {index_offset:016x} 00000000 {key:x}\n'.encode())

        f.seek(index_offset)
        f.write(index_data)

    return filepath


class TestRpaReader(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_invalid_header(self):
        path = os.path.join(self.tmpdir, 'bad.rpa')
        with open(path, 'wb') as f:
            f.write(b'NOTRPA! 0000000000000000\n')
            f.write(b'\x00' * 100)

        with self.assertRaises(InvalidHeaderError):
            with RpaReader(path):
                pass

    def test_rpa_30_with_key(self):
        files = {'test/hello.txt': b'Hello!'}
        path = _create_test_rpa(self.tmpdir, '3.0', key=0x42424242, files=files)
        with RpaReader(path) as reader:
            self.assertEqual(reader.version, 3.0)
            entries = reader.get_entries()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].path, 'test/hello.txt')
            data = reader.read_file_data(entries[0])
            self.assertEqual(data, b'Hello!')

    def test_rpa_20_no_xor(self):
        files = {'test/hello.txt': b'World!'}
        path = _create_test_rpa(self.tmpdir, '2.0', files=files)
        with RpaReader(path) as reader:
            self.assertEqual(reader.version, 2.0)
            entries = reader.get_entries()
            self.assertEqual(len(entries), 1)
            data = reader.read_file_data(entries[0])
            self.assertEqual(data, b'World!')

    def test_multiple_files(self):
        files = {
            'a.txt': b'AAA',
            'b.txt': b'BBB',
            'subdir/c.txt': b'CCC',
        }
        path = _create_test_rpa(self.tmpdir, '3.0', files=files)
        with RpaReader(path) as reader:
            entries = reader.get_entries()
            self.assertEqual(len(entries), 3)
            paths = sorted(e.path for e in entries)
            self.assertEqual(paths, ['a.txt', 'b.txt', 'subdir/c.txt'])


if __name__ == '__main__':
    unittest.main()
