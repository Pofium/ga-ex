"""Unpacker для Majiro Arc V3 (.arc) — движок японских визуальных новелл.

Формат:
  Header (32 байта):
    Magic "MajiroArcV3.000\0" (16 bytes)
    Entry count (uint16 LE)
    Zero (uint16 LE)
    Name table offset (uint32 LE)
    Total data size (uint32 LE)
    CRC32 (uint32 LE)

  После хедера (с байта 32):
    Таблица: entry_count × 12 байт
      Каждая запись: {uint32 unknown, uint32 offset, uint32 size}

  Name table (по name table offset):
    entry_count null-terminated имён (Shift-JIS)

  Данные файлов — по абсолютным оффсетам из таблицы.
"""
from __future__ import annotations

import os
import struct
from typing import List, Optional

from core.base_unpacker import (
    BaseUnpacker, UnpackOptions, UnpackResult, ProgressCallback,
)

MAJIRO_MAGIC = b'MajiroArcV3.000\x00'
HEADER_SIZE = 32
ENTRY_SIZE = 12


class MajiroArcUnpacker(BaseUnpacker):
    """Распаковщик Majiro Arc V3 (.arc) архивов."""

    name = 'majiro'

    @classmethod
    def detect(cls, target: str) -> bool:
        if not os.path.isfile(target):
            return False
        try:
            with open(target, 'rb') as f:
                head = f.read(16)
            return head == MAJIRO_MAGIC[:16]
        except (OSError, PermissionError):
            return False

    def analyze(self, target: str) -> dict:
        info = {
            'type': 'majiro_arc',
            'detected': self.detect(target),
            'file_size': os.path.getsize(target) if os.path.isfile(target) else 0,
            'error': None,
        }
        if not info['detected']:
            return info
        try:
            with open(target, 'rb') as f:
                header_data = f.read(HEADER_SIZE)
            entry_count = struct.unpack_from('<H', header_data, 16)[0]
            list_offset = struct.unpack_from('<I', header_data, 20)[0]
            info['entry_count'] = entry_count
            info['name_table_offset'] = list_offset

            # Читаем имена для сэмпла
            with open(target, 'rb') as f:
                f.seek(list_offset)
                name_data = f.read(4096)
            names = []
            pos = 0
            for _ in range(min(entry_count, 10)):
                end = name_data.find(b'\x00', pos)
                if end == -1:
                    break
                names.append(
                    name_data[pos:end].decode('shift-jis', errors='replace')
                )
                pos = end + 1
            info['sample_names'] = names
            if entry_count > 10:
                info['sample_names'].append(f'... (+{entry_count - 10} more)')
        except Exception as e:
            info['error'] = f'{type(e).__name__}: {e}'
        return info

    def unpack(
        self,
        target: str,
        options: UnpackOptions,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> UnpackResult:
        result = UnpackResult(success=False, output_dir=options.output_dir)

        if not self.detect(target):
            result.errors.append(
                f'{os.path.basename(target)}: не Majiro Arc V3 (нет магии)'
            )
            return result

        output_dir = options.output_dir
        os.makedirs(output_dir, exist_ok=True)

        arc_basename = os.path.splitext(
            os.path.basename(target)
        )[0]

        try:
            with open(target, 'rb') as f:
                # Читаем хедер
                header_data = f.read(HEADER_SIZE)
            entry_count = struct.unpack_from('<H', header_data, 16)[0]
            list_offset = struct.unpack_from('<I', header_data, 20)[0]
        except (OSError, PermissionError) as e:
            result.errors.append(f'{os.path.basename(target)}: {e}')
            return result

        if entry_count == 0:
            result.warnings.append(
                f'{os.path.basename(target)}: пустой архив (0 записей)'
            )
            result.success = True
            return result

        # Читаем таблицу смещений и размеров
        entries = []
        with open(target, 'rb') as f:
            f.seek(HEADER_SIZE)
            table_data = f.read(entry_count * ENTRY_SIZE)
        for i in range(entry_count):
            unknown, offset, size = struct.unpack_from(
                '<III', table_data, i * ENTRY_SIZE
            )
            entries.append((unknown, offset, size))

        # Читаем таблицу имён
        with open(target, 'rb') as f:
            f.seek(list_offset)
            name_data = f.read(min(65536, os.path.getsize(target) - list_offset))
        names = []
        pos = 0
        for _ in range(entry_count):
            end = name_data.find(b'\x00', pos)
            if end == -1:
                names.append(f'unknown_{len(names):04d}')
                pos = len(name_data)
                continue
            try:
                name = name_data[pos:end].decode('shift-jis')
            except UnicodeDecodeError:
                name = name_data[pos:end].decode('shift-jis', errors='replace')
            names.append(name)
            pos = end + 1

        # Извлекаем файлы
        fz = os.path.getsize(target)
        for idx, ((_, b_field, c_field), name) in enumerate(
            zip(entries, names), 1
        ):
            # Эвристика: оффсет может быть в поле b или c
            # - b_field: абсолютный оффсет от начала файла (обычный случай)
            # - c_field: иногда используется для хранения оффсета в конце архива
            offset = b_field if b_field < fz else c_field
            if offset >= fz:
                # Оба поля вне границ — пробуем очистить старший бит
                offset_alt = c_field & 0x7FFFFFFF if c_field & 0x80000000 else c_field
                if offset_alt < fz:
                    offset = offset_alt
                else:
                    result.warnings.append(
                        f'{name}: offset+size выходит за границы архива '
                        f'(offset=0x{offset:x} size={c_field})'
                    )
                    continue

            size = c_field
            if size == 0:
                result.warnings.append(f'{name}: пустой файл (size=0)')
                continue
            if offset + size > fz:
                result.warnings.append(
                    f'{name}: offset+size выходит за границы архива '
                    f'(offset=0x{offset:x} size={size})'
                )
                continue

            try:
                with open(target, 'rb') as f:
                    f.seek(offset)
                    data = f.read(size)
            except (OSError, PermissionError) as e:
                result.errors.append(f'{name}: ошибка чтения: {e}')
                if not options.continue_on_error:
                    return result
                continue

            if len(data) != size:
                result.warnings.append(
                    f'{name}: прочитано {len(data)} из {size} байт'
                )

            # Безопасный путь из имени файла
            safe_parts = []
            for part in name.replace('\\', '/').split('/'):
                part = part.strip()
                if not part:
                    continue
                if '..' in part:
                    result.skipped.append({
                        'path': name,
                        'reason': 'path traversal blocked',
                    })
                    continue
                safe = ''.join(
                    c for c in part if c.isalnum() or c in '._- ()[]'
                )
                safe_parts.append(safe)

            # Создаём подпапку по имени архива
            subdir = os.path.join(output_dir, arc_basename)
            os.makedirs(subdir, exist_ok=True)

            out_path = os.path.join(subdir, '/'.join(safe_parts))
            out_parent = os.path.dirname(out_path)
            if out_parent:
                os.makedirs(out_parent, exist_ok=True)

            try:
                with open(out_path, 'wb') as f:
                    f.write(data)
            except OSError as e:
                result.errors.append(f'{name}: ошибка записи: {e}')
                if not options.continue_on_error:
                    return result
                continue

            result.files_extracted.append(out_path)

            if progress_callback:
                try:
                    progress_callback(name, idx, entry_count)
                except Exception:
                    pass

        result.success = len(result.errors) == 0
        return result
