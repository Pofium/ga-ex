"""Чтение .xp3 архивов (формат движка KiriKiri / 吉里吉里).

XP3 (XP3 Archive) — формат архивов японского движка визуальных новелл KiriKiri.
Структура (по krkrz/krkrz base/XP3Archive.cpp):

  [11 байт: magic 'XP3\\r\\n \\n\\x1a\\x8b\\x67\\x01']
  [8 байт: index_ofs (uint64 LE) — смещение до первого Index Record]
  [Index Record chain — читается пока в index_flag установлен бит 0x80 CONTINUE]
    Каждый Index Record:
      [1 байт: index_flag]
        биты 0x0F: метод сжатия индекса (0=raw, 1=zlib)
        бит 0x80: CONTINUE — есть следующий Index Record
      [8 байт: size (для raw: raw_size, для zlib: compressed_size)]
      [если zlib: 8 байт raw_size]
      [size байт: данные индекса (zlib или raw)]

  Index data — последовательность chunks (file/info/segm/adlr/time):
    [4 байт tag] [8 байт chunk_size] [chunk_size байт data]

    FILE chunk: контейнер для sub-chunks
    INFO chunk: flags(4) + OrgSize(8) + ArcSize(8) + name_len(2) + name(UTF-16LE)
    SEGM chunk: массив сегментов по 28 байт:
      flags(4) + Start/offset(8) + OrgSize(8) + ArcSize(8)
    ADLR chunk: 4-байтовый hash
    TIME chunk: 8 байт timestamp

Сжатие: zlib (deflate).
Шифрование: опциональное (cypher) — не поддерживается в этой реализации.
Имена: UTF-16LE.
"""
from __future__ import annotations

import io
import os
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator, List, Optional, Tuple, Union


# Magic: XP3\r\n \n\x1a\x8b\x67\x01 (11 байт)
XP3_MAGIC = b'XP3\r\n \n\x1a\x8b\x67\x01'

# Chunk tags в Index (uint32 little-endian).
# "File" = 0x46 0x69 0x6C 0x65 → LE 0x656C6946
TAG_FILE = 0x656C6946  # 'File'
TAG_INFO = 0x6F666E69  # 'info'
TAG_SEGM = 0x6D676573  # 'segm'
TAG_ADLR = 0x726C6461  # 'adlr'
TAG_TIME = 0x656D6974  # 'time'

# Info flags
INFO_FLAG_ENCRYPTED = 0x80000000
INFO_FLAG_PROTECTED = 0x40000000
INFO_FLAG_COMPRESSED = 0x00000001


@dataclass
class Xp3Entry:
    """Описание одного файла внутри .xp3 архива."""
    path: str               # относительный путь (UTF-8), как сохранён в индексе
    offset: int             # абсолютное смещение данных в архиве (первого сегмента)
    size: int               # размер сжатых данных в архиве (сумма archive_size сегментов)
    original_size: int      # размер распакованных данных (из INFO.OrgSize)
    compressed: bool        # True если INFO_FLAG_COMPRESSED (хотя бы один сегмент сжат)
    # Сегменты: для .xp3 у каждого entry может быть несколько сегментов,
    # но в большинстве случаев — один. Поддерживаем список.
    # Каждый сегмент: (offset_in_archive, archive_size, original_size, is_compressed)
    segments: List[tuple]


class Xp3Error(Exception):
    """Базовый класс ошибок XP3."""


class Xp3InvalidFileError(Xp3Error):
    """Файл не является XP3 или повреждён."""


class Xp3UnsupportedError(Xp3Error):
    """Возможности формата не поддерживаются (например, шифрование)."""


class Xp3Reader:
    """Читатель XP3 архива. Использует lazy-чтение индекса при первом обращении."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self._file: Optional[BinaryIO] = None
        self._entries: List[Xp3Entry] = []
        self._index_loaded = False

    # ---- lifecycle ----

    def __enter__(self) -> 'Xp3Reader':
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def _open(self) -> BinaryIO:
        if self._file is None:
            self._file = open(self.filepath, 'rb')
        return self._file

    # ---- public API ----

    @staticmethod
    def detect(filepath: Union[str, Path]) -> bool:
        """Быстрая проверка сигнатуры (без загрузки всего индекса).

        Args:
            filepath: Путь к .xp3 файлу.

        Returns:
            True если файл начинается с правильной сигнатуры XP3.
        """
        try:
            with open(filepath, 'rb') as f:
                sig = f.read(len(XP3_MAGIC))
            return sig == XP3_MAGIC
        except (OSError, PermissionError):
            return False

    def get_entries(self) -> List[Xp3Entry]:
        """Возвращает список всех файлов в архиве (загружает индекс если нужно)."""
        if not self._index_loaded:
            self._load_index()
        return list(self._entries)

    def read_file_data(self, entry: Xp3Entry) -> bytes:
        """Читает и при необходимости декомпрессирует данные одного файла.

        Сегменты в entry.segments имеют формат:
          (offset, archive_size, original_size, is_compressed)
        Сегменты конкатенируются в порядке следования; каждый сжатый сегмент
        декомпрессируется отдельно.
        """
        f = self._open()
        chunks = []
        for seg in entry.segments:
            offset, arc_size, org_size, is_compressed = seg
            f.seek(offset)
            data = f.read(arc_size)
            if is_compressed:
                data = _decompress_segment(data, org_size)
            chunks.append(data)
        return b''.join(chunks)

    def file_size(self) -> int:
        return os.path.getsize(self.filepath)

    # ---- index parsing ----

    def _load_index(self) -> None:
        """Загружает и парсит Index Section.

        Формат (по krkrz/krkrz base/XP3Archive.cpp):
        - 11 байт: magic
        - 8 байт: index_ofs (uint64 LE) — смещение до первого Index Record
        - Цепочка Index Records, читаемых до тех пор, пока в index_flag не установлен
          бит CONTINUE (0x80). Каждый Index Record:
            * 1 байт: index_flag
              - low 4 bits (0x0F): метод сжатия индекса (0=raw, 1=zlib)
              - bit 0x80: CONTINUE — есть ещё один index_ofs сразу после Record
            * 8 байт: index_size (raw_size если raw; compressed_size если zlib)
            * если zlib: ещё 8 байт raw_size
            * index_size байт данных индекса
        """
        f = self._open()
        file_size = os.fstat(f.fileno()).st_size

        # Первый index_ofs — сразу после magic
        f.seek(11)
        header = f.read(8)
        if len(header) != 8:
            raise Xp3InvalidFileError('XP3 index offset missing')
        index_ofs = struct.unpack('<Q', header)[0]

        while True:
            if not (0 < index_ofs < file_size):
                raise Xp3InvalidFileError(
                    f'XP3 index offset {index_ofs} out of range (file size {file_size})'
                )

            f.seek(index_ofs)
            flag_byte = f.read(1)
            if not flag_byte:
                raise Xp3InvalidFileError('XP3 index flag missing')
            flag = flag_byte[0]
            method = flag & 0x0F
            has_continue = bool(flag & 0x80)

            if method == 0x01:
                # zlib-сжатый индекс
                size_buf = f.read(16)
                if len(size_buf) != 16:
                    raise Xp3InvalidFileError('XP3 zlib index sizes missing')
                compressed_size, raw_size = struct.unpack('<QQ', size_buf)
                compressed = f.read(compressed_size)
                if len(compressed) != compressed_size:
                    raise Xp3InvalidFileError(
                        f'XP3 zlib index data truncated: {len(compressed)}/{compressed_size}'
                    )
                try:
                    index_data = zlib.decompress(compressed)
                except zlib.error as e:
                    raise Xp3InvalidFileError(
                        f'XP3 index zlib decompression failed: {e}'
                    )
                if len(index_data) != raw_size:
                    # Не критично: некоторые тулзы неверно указывают raw_size
                    pass
            elif method == 0x00:
                # raw (несжатый) индекс
                size_buf = f.read(8)
                if len(size_buf) != 8:
                    raise Xp3InvalidFileError('XP3 raw index size missing')
                (raw_size,) = struct.unpack('<Q', size_buf)
                index_data = f.read(raw_size)
                if len(index_data) != raw_size:
                    raise Xp3InvalidFileError(
                        f'XP3 raw index data truncated: {len(index_data)}/{raw_size}'
                    )
            else:
                raise Xp3UnsupportedError(
                    f'XP3 index encode method 0x{method:x} not supported'
                )

            # Парсим текущую порцию индекса
            self._parse_index(index_data)

            if not has_continue:
                break

            # CONTINUE: следующие 8 байт = index_ofs следующего Record
            next_ofs_buf = f.read(8)
            if len(next_ofs_buf) != 8:
                raise Xp3InvalidFileError('XP3 continuation index offset missing')
            index_ofs = struct.unpack('<Q', next_ofs_buf)[0]

        self._index_loaded = True

    def _parse_index(self, data: bytes) -> None:
        """Парсит Index data: иерархия chunks (file / {info, segm, adlr, time}).

        Структура (по krkrz):
          [FILE tag(4)] [FILE size(8)] [FILE data = {sub-chunks}]
          [FILE tag(4)] [FILE size(8)] [FILE data = {sub-chunks}]
          ...

        Внутри FILE data:
          [sub-chunk tag(4)] [sub-chunk size(8)] [sub-chunk data]
          ...

        Каждый sub-chunk:
          info: flags(4) + OrgSize(8) + ArcSize(8) + name_len(2) + name(UTF-16LE)
          segm: массив по 28 байт = flags(4) + Start(8) + OrgSize(8) + ArcSize(8)
          adlr: 4-байтовый hash
          time: 8 байт timestamp
        """
        pos = 0
        end = len(data)
        while pos < end:
            try:
                tag, size, pos = self._read_chunk_header(data, pos, end)
            except Xp3InvalidFileError:
                break

            if tag == TAG_FILE:
                file_data_end = pos + size
                if file_data_end > end:
                    raise Xp3InvalidFileError(
                        f'XP3 file chunk extends past index: {file_data_end} > {end}'
                    )
                # Парсим sub-chunks внутри FILE
                self._parse_file_chunk(data, pos, file_data_end)
                pos = file_data_end
            else:
                # Неизвестный top-level chunk — пропускаем
                pos += size

    def _parse_file_chunk(self, data: bytes, start: int, end: int) -> None:
        """Парсит sub-chunks одного FILE entry (info, segm, adlr, time)."""
        current: dict = {'name': None, 'info': None, 'segm': [], 'adlr': None}
        pos = start

        while pos < end:
            try:
                tag, size, pos = self._read_chunk_header(data, pos, end)
            except Xp3InvalidFileError:
                break
            chunk_data = data[pos:pos + size]
            if len(chunk_data) != size:
                raise Xp3InvalidFileError(
                    f'XP3 sub-chunk truncated: tag=0x{tag:08x}'
                )

            if tag == TAG_INFO:
                self._parse_info(chunk_data, current)
            elif tag == TAG_SEGM:
                self._parse_segm(chunk_data, current)
            elif tag == TAG_ADLR:
                if size >= 4:
                    current['adlr'] = struct.unpack('<I', chunk_data[:4])[0]
            elif tag == TAG_TIME:
                pass  # игнорируем timestamp
            else:
                pass  # неизвестный sub-chunk — пропускаем

            pos += size

        # Сохраняем entry если есть имя и сегменты
        if current.get('name') and current.get('segm'):
            self._add_entry(current)

    @staticmethod
    def _read_chunk_header(data: bytes, pos: int, end: int) -> Tuple[int, int, int]:
        """Читает заголовок chunk (tag(4) + size(8)). Возвращает (tag, size, new_pos)."""
        if pos + 12 > end:
            raise Xp3InvalidFileError('XP3 chunk header truncated')
        tag, size = struct.unpack('<IQ', data[pos:pos + 12])
        return tag, size, pos + 12

    @staticmethod
    def _parse_info(chunk_data: bytes, current: dict) -> None:
        """Парсит info sub-chunk: flags(4) + OrgSize(8) + ArcSize(8) + name_len(2) + name."""
        if len(chunk_data) < 22:
            raise Xp3InvalidFileError(f'XP3 info chunk too small: {len(chunk_data)}')
        flags = struct.unpack('<I', chunk_data[:4])[0]
        org_size = struct.unpack('<Q', chunk_data[4:12])[0]
        arc_size = struct.unpack('<Q', chunk_data[12:20])[0]
        name_len = struct.unpack('<H', chunk_data[20:22])[0]
        need = 22 + name_len * 2
        if len(chunk_data) < need:
            raise Xp3InvalidFileError(
                f'XP3 info chunk name truncated: need {need}, have {len(chunk_data)}'
            )
        name_bytes = chunk_data[22:need]
        try:
            name = name_bytes.decode('utf-16-le').replace('\\', '/')
        except UnicodeDecodeError:
            name = None
        encrypted = bool(flags & INFO_FLAG_ENCRYPTED)
        if encrypted:
            raise Xp3UnsupportedError('Encrypted XP3 not supported')
        compressed = bool(flags & INFO_FLAG_COMPRESSED)
        current['info'] = {
            'flags': flags,
            'compressed': compressed,
            'original_size': org_size,
            'archive_size': arc_size,
        }
        current['name'] = name

    @staticmethod
    def _parse_segm(chunk_data: bytes, current: dict) -> None:
        """Парсит segm sub-chunk: массив сегментов по 28 байт."""
        if len(chunk_data) % 28 != 0:
            raise Xp3InvalidFileError(
                f'XP3 segm chunk size {len(chunk_data)} is not multiple of 28'
            )
        seg_count = len(chunk_data) // 28
        for i in range(seg_count):
            base = i * 28
            seg_flags = struct.unpack('<I', chunk_data[base:base + 4])[0]
            seg_start = struct.unpack('<Q', chunk_data[base + 4:base + 12])[0]
            seg_org = struct.unpack('<Q', chunk_data[base + 12:base + 20])[0]
            seg_arc = struct.unpack('<Q', chunk_data[base + 20:base + 28])[0]
            # low 2 bits of flags = encode method: 0=raw, 1=zlib
            seg_compressed = bool(seg_flags & 0x01)
            current['segm'].append({
                'offset': seg_start,
                'original_size': seg_org,
                'archive_size': seg_arc,
                'compressed': seg_compressed,
            })

    def _add_entry(self, current: dict) -> None:
        """Создаёт Xp3Entry из накопленных данных."""
        name = current.get('name')
        segm = current.get('segm')
        info = current.get('info') or {}
        if not name or not segm:
            return
        compressed = bool(info.get('compressed', False))
        original_size = int(info.get('original_size') or 0)
        # Совместимость со старым кодом: первый offset и сумма размеров
        offset = segm[0]['offset']
        # Полный размер данных = сумма archive_size сегментов
        size = sum(s['archive_size'] for s in segm)
        # Совместимый список сегментов: (offset, size) кортежи
        segments = [
            (s['offset'], s['archive_size'], s['original_size'], s['compressed'])
            for s in segm
        ]
        entry = Xp3Entry(
            path=name,
            offset=offset,
            size=size,
            original_size=original_size or sum(s['original_size'] for s in segm),
            compressed=compressed,
            segments=segments,
        )
        self._entries.append(entry)


def _decompress_segment(data: bytes, original_size: int) -> bytes:
    """Распаковывает сегмент XP3 (zlib-обёртка с префиксом-размером).

    В .xp3 упакованные данные имеют структуру:
      [uint32 compressed_size_le]  — но в разных реализациях либо есть, либо нет
      [zlib compressed data]

    Реальный KiriKiri формат: сначала идёт сжатый поток, БЕЗ префикса размера.
    Размер записан в info.original_size.
    """
    # Пробуем напрямую zlib
    try:
        return zlib.decompress(data)
    except zlib.error:
        pass
    # Пробуем отрезать 4 байта префикса (некоторые тулзы добавляют)
    if len(data) > 4:
        try:
            return zlib.decompress(data[4:])
        except zlib.error:
            pass
    raise Xp3InvalidFileError('Cannot decompress XP3 segment')
