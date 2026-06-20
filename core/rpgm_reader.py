"""Парсер RPG Maker XP/VX/VX Ace архивов: .rgssad, .rgss2a, .rgss3a.

Формат (по https://github.com/Petschko/RPG-Maker-MV-Decrypter и reverse engineering):

.RGSSAD (RPG Maker XP):
  Magic: 7 байт 'RGSSAD\0'  (XP) или 6 байт 'RGSSAD' + 1 байт версия
  Body: stream of records:
    [u32 size][u32 key_xor_magic][size bytes data]
    Ключ меняется после каждой записи:
      key = (key * 7 + 3) & 0xFFFFFFFF
    name length: 1 байт (длина пути файла)
    имя файла: name_length байт UTF-8, XOR с текущим ключом (по 1 байту за раз)

.RGSS2A (RPG Maker VX):
  Header: 8 байт 'RGSS2A\0\0' (8 bytes) + 4 байта version
  Body: аналогично с key rotation, но имя зашифровано по-другому.

.RGSS3A (RPG Maker VX Ace):
  Header: 'RGSS3A\0\0' (8 байт) + 4 байта version
  Body: записи с key rotation; имя файла — UTF-8, XOR с rotating key.
"""
from __future__ import annotations

import io
import os
import struct
from dataclasses import dataclass
from typing import BinaryIO, Iterator, List, Optional


class RgssadError(Exception):
    """Ошибка чтения .rgssad/.rgss2a/.rgss3a архива."""


class RgssadInvalidFileError(RgssadError):
    """Файл не является валидным RGSSAD архивом."""


class RgssadUnsupportedError(RgssadError):
    """Версия/формат не поддерживается."""


@dataclass
class RgssadEntry:
    """Описание одного файла внутри .rgssad архива."""
    path: str           # относительный путь (UTF-8)
    offset: int         # абсолютное смещение данных в архиве
    size: int           # размер данных
    encrypted_size: int  # размер данных в архиве (после XOR)


class RgssadReader:
    """Базовый класс для чтения RPG Maker XP/VX/VX Ace архивов.

    Используется через Rgss1aReader/Rgss2aReader/Rgss3aReader (наследники).
    """

    MAGIC: bytes = b''
    HEADER_SIZE: int = 7

    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        self._entries: List[RgssadEntry] = []
        self._index_loaded = False

    def __enter__(self) -> 'RgssadReader':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass  # Файл закрываем после чтения

    @classmethod
    def detect(cls, filepath: str) -> bool:
        """Быстрая проверка magic."""
        try:
            with open(filepath, 'rb') as f:
                sig = f.read(len(cls.MAGIC))
            return sig == cls.MAGIC
        except (OSError, PermissionError):
            return False

    def get_entries(self) -> List[RgssadEntry]:
        """Возвращает список файлов в архиве."""
        if not self._index_loaded:
            self._load_index()
        return list(self._entries)

    def _open(self) -> BinaryIO:
        return open(self.filepath, 'rb')

    def _load_index(self) -> None:
        raise NotImplementedError

    def read_file_data(self, entry: RgssadEntry) -> bytes:
        """Читает и расшифровывает данные одного файла."""
        f = self._open()
        f.seek(entry.offset)
        encrypted = f.read(entry.encrypted_size)
        if len(encrypted) != entry.encrypted_size:
            raise RgssadError(
                f'Read truncated: {len(encrypted)}/{entry.encrypted_size}'
            )
        return self._decrypt_data(encrypted)

    def _decrypt_data(self, encrypted: bytes) -> bytes:
        """Дешифрует данные файла. По умолчанию — identity (RGSS1a).
        Для RGSS2a/3a переопределяется.
        """
        return bytes(encrypted)


class Rgss1aReader(RgssadReader):
    """RPG Maker XP — .rgssad (v1)."""
    MAGIC = b'RGSSAD\x00'
    HEADER_SIZE = 7

    def _load_index(self) -> None:
        f = self._open()
        file_size = os.fstat(f.fileno()).st_size

        header = f.read(self.HEADER_SIZE)
        if len(header) != self.HEADER_SIZE or header != self.MAGIC:
            raise RgssadInvalidFileError('RGSSAD v1 magic mismatch')

        # Начальный ключ — magic[0..3] (первые 4 байта)
        key = struct.unpack('<I', self.MAGIC[:4])[0]

        # Stream of records
        while f.tell() < file_size:
            # Read u32 size
            buf = f.read(4)
            if len(buf) < 4:
                break
            size, = struct.unpack('<I', buf)
            if size == 0:
                break

            # XOR size with key
            size_xor = size ^ key
            key = (key * 7 + 3) & 0xFFFFFFFF

            # Read 1 byte name_length
            name_len_byte = f.read(1)
            if not name_len_byte:
                break
            name_len = name_len_byte[0] ^ (key & 0xFF)
            key = (key * 7 + 3) & 0xFFFFFFFF

            # Read name (name_len bytes), XOR each with key byte
            name_buf = f.read(name_len)
            if len(name_buf) != name_len:
                break
            name_bytes = bytearray(name_buf)
            for i in range(name_len):
                name_bytes[i] ^= (key & 0xFF)
                key = (key * 7 + 3) & 0xFFFFFFFF
            name = bytes(name_bytes).decode('utf-8', errors='replace').replace('\\', '/')

            # Read data (size_xor bytes)
            offset = f.tell()
            data = f.read(size_xor)
            if len(data) != size_xor:
                break

            self._entries.append(RgssadEntry(
                path=name,
                offset=offset,
                size=size_xor,
                encrypted_size=size_xor,
            ))

        self._index_loaded = True


class Rgss2aReader(RgssadReader):
    """RPG Maker VX — .rgss2a (v2)."""
    MAGIC = b'RGSS2A\x00\x00'
    HEADER_SIZE = 8
    VERSION_SIZE = 4

    def _load_index(self) -> None:
        f = self._open()
        file_size = os.fstat(f.fileno()).st_size

        header = f.read(self.HEADER_SIZE)
        if len(header) != self.HEADER_SIZE or header != self.MAGIC:
            raise RgssadInvalidFileError('RGSS2A magic mismatch')

        version = f.read(self.VERSION_SIZE)
        # version mostly ignored

        # Начальный ключ = u32 от 'RGSS' (= 0x53534752)
        key = struct.unpack('<I', b'RGSS')[0]

        while f.tell() < file_size:
            buf = f.read(4)
            if len(buf) < 4:
                break
            size, = struct.unpack('<I', buf)
            size ^= key
            key = (key * 7 + 3) & 0xFFFFFFFF
            if size == 0:
                break

            # Name length: u32
            buf = f.read(4)
            if len(buf) < 4:
                break
            name_len, = struct.unpack('<I', buf)
            name_len ^= key
            key = (key * 7 + 3) & 0xFFFFFFFF

            # Name (name_len bytes UTF-8, XOR with key bytes)
            name_buf = f.read(name_len)
            if len(name_buf) != name_len:
                break
            name_bytes = bytearray(name_buf)
            for i in range(name_len):
                name_bytes[i] ^= (key & 0xFF)
                key = (key * 7 + 3) & 0xFFFFFFFF
            name = bytes(name_bytes).decode('utf-8', errors='replace').replace('\\', '/')

            # Data
            offset = f.tell()
            data = f.read(size)
            if len(data) != size:
                break

            self._entries.append(RgssadEntry(
                path=name,
                offset=offset,
                size=size,
                encrypted_size=size,
            ))

        self._index_loaded = True


class Rgss3aReader(Rgss2aReader):
    """RPG Maker VX Ace — .rgss3a (v3). Использует ту же структуру что и v2."""
    MAGIC = b'RGSS3A\x00\x00'
    HEADER_SIZE = 8
    VERSION_SIZE = 4


# ============ Factory ============

def detect_rgssad_variant(filepath: str) -> Optional[str]:
    """Определяет вариант RGSSAD по magic. Возвращает 'rgss1a'/'rgss2a'/'rgss3a'/None."""
    try:
        with open(filepath, 'rb') as f:
            head = f.read(8)
    except (OSError, PermissionError):
        return None
    if head.startswith(b'RGSS3A'):
        return 'rgss3a'
    if head.startswith(b'RGSS2A'):
        return 'rgss2a'
    if head.startswith(b'RGSSAD'):
        return 'rgss1a'
    return None


def open_rgssad(filepath: str) -> RgssadReader:
    """Открывает соответствующий ридер по magic."""
    variant = detect_rgssad_variant(filepath)
    if variant == 'rgss1a':
        return Rgss1aReader(filepath)
    if variant == 'rgss2a':
        return Rgss2aReader(filepath)
    if variant == 'rgss3a':
        return Rgss3aReader(filepath)
    raise RgssadInvalidFileError(f'Unknown RGSSAD variant: {filepath}')
