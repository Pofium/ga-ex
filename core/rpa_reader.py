import struct
import zlib
import pickle
import os
from typing import List, Dict, Any, Tuple
from core.errors import InvalidHeaderError, InvalidIndexError


class RpaEntry:
    def __init__(self, path: str, offset: int, length: int):
        self.path = path
        self.offset = offset
        self.length = length


class RpaReader:
    RPA_20_SIGNATURE = b'RPA-2.0 '
    RPA_30_SIGNATURE = b'RPA-3.0 '
    RPA_32_SIGNATURE = b'RPA-3.2 '

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.version = None
        self.index_offset = None
        self.key = 0
        self.entries: List[RpaEntry] = []
        self._file = None
        self._file_size = 0

    def open(self) -> None:
        self._file = open(self.filepath, 'rb')
        try:
            self._file.seek(0, os.SEEK_END)
            self._file_size = self._file.tell()
            self._file.seek(0)
            self._read_header()
            self._read_index()
        except Exception:
            self._file.close()
            self._file = None
            raise

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def _read_header(self) -> None:
        self._file.seek(0)
        header_bytes = self._file.readline()
        try:
            header = header_bytes.decode('utf-8').strip()
        except UnicodeDecodeError:
            raise InvalidHeaderError("Invalid RPA header encoding")

        vals = header.split()
        if not vals:
            raise InvalidHeaderError("Empty RPA header")

        magic = vals[0]
        if magic == 'RPA-3.2':
            self.version = 3.2
        elif magic == 'RPA-3.0' or magic == 'RPA-4.0':
            self.version = 3.0
        elif magic == 'RPA-2.0':
            self.version = 2.0
        else:
            raise InvalidHeaderError(f"Invalid RPA header: {magic}. Expected RPA-2.0, RPA-3.0 or RPA-3.2")

        if len(vals) < 2:
            raise InvalidHeaderError("Header missing index offset")

        try:
            self.index_offset = int(vals[1], 16)
        except ValueError:
            raise InvalidHeaderError(f"Cannot parse index offset from header: {vals[1]}")

        self.key = 0
        if self.version == 3.0:
            for subkey in vals[2:]:
                self.key ^= int(subkey, 16)
        elif self.version == 3.2:
            for subkey in vals[3:]:
                self.key ^= int(subkey, 16)

    def _read_index(self) -> None:
        """Читает индекс: zlib-decompress (БЕЗ XOR), затем pickle."""
        self._file.seek(self.index_offset)
        index_data = self._file.read()
        if not index_data:
            raise InvalidIndexError("Index data is empty")

        try:
            decompressed = zlib.decompress(index_data)
        except zlib.error as e:
            raise InvalidIndexError(f"Failed to decompress index: {e}")

        try:
            index = pickle.loads(decompressed)
        except Exception as e:
            raise InvalidIndexError(f"Failed to unpickle index: {e}")

        self._parse_index(index)

    def _decode_value(self, encoded: int) -> int:
        if self.version >= 3.0:
            return encoded ^ self.key
        return encoded

    def _parse_index(self, index: Any) -> None:
        if not isinstance(index, dict):
            raise InvalidIndexError(f"Unexpected index format: expected dict, got {type(index)}")

        for path, entries in index.items():
            if not isinstance(path, str):
                continue

            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                        enc_offset = entry[0]
                        enc_length = entry[1]

                        real_offset = self._decode_value(enc_offset)
                        real_length = self._decode_value(enc_length)

                        if real_offset > 0 and real_length > 0:
                            self.entries.append(RpaEntry(path, real_offset, real_length))

    def get_entries(self) -> List[RpaEntry]:
        return self.entries

    def read_file_data(self, entry: RpaEntry) -> bytes:
        self._file.seek(entry.offset)
        return self._file.read(entry.length)


def list_files(filepath: str) -> List[str]:
    with RpaReader(filepath) as reader:
        return [entry.path for entry in reader.get_entries()]
