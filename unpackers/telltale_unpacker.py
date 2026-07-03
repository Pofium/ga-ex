"""Unpacker для Telltale .ttarch архивов (T3GZ формат).

Формат .ttarch:
  Используется в играх Telltale (The Walking Dead, Wolf Among Us, etc.)
  
  Заголовок (16+ байт):
    Magic "T3GZ" (4 bytes)
    Version (uint32 LE — обычно 1)
    Offset таблицы объектов (uint32 LE)
    Количество объектов (uint32 LE)
    Flags (uint32 LE) — 0=нет сжатия, 1=zlib

  Таблица объектов (offset × ObjectSize на запись):
    Размер в архиве (uint32 LE)
    Оригинальный размер (uint32 LE)  
    Флаги (uint32 LE)
    Хеш имени (может быть)
    Offset данных (uint32 LE)

  Имена файлов хранятся отдельно (часто с хешами).
  Файлы без сжатия кладутся as-is; с zlib — декомпрессируются.
"""
from __future__ import annotations

import os
import struct
import zlib
from typing import List, Optional

from core.base_unpacker import (
    BaseUnpacker, UnpackOptions, UnpackResult, ProgressCallback,
)

TELLTALE_MAGIC = b'T3GZ'


class TelltaleUnpacker(BaseUnpacker):
    """Распаковщик Telltale .ttarch архивов."""

    name = 'telltale'

    @classmethod
    def detect(cls, target: str) -> bool:
        if not os.path.isfile(target):
            return False
        if not target.lower().endswith('.ttarch'):
            return False
        try:
            with open(target, 'rb') as f:
                head = f.read(4)
            return head == TELLTALE_MAGIC
        except (OSError, PermissionError):
            return False

    def analyze(self, target: str) -> dict:
        info = {
            'type': 'telltale_ttarch',
            'detected': self.detect(target),
            'file_size': os.path.getsize(target) if os.path.isfile(target) else 0,
            'error': None,
        }
        if not info['detected']:
            return info
        try:
            with open(target, 'rb') as f:
                header = f.read(16)
            version = struct.unpack_from('<I', header, 4)[0]
            obj_offset = struct.unpack_from('<I', header, 8)[0]
            obj_count = struct.unpack_from('<I', header, 12)[0]
            info['version'] = version
            info['object_count'] = obj_count
            info['object_table_offset'] = obj_offset
            flags = struct.unpack_from('<I', header, 16)[0] if len(header) > 16 else 0
            info['flags'] = flags
            info['compression'] = 'zlib' if flags & 1 else 'none'
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
                f'{os.path.basename(target)}: не Telltale TTArch'
            )
            return result

        output_dir = options.output_dir
        os.makedirs(output_dir, exist_ok=True)

        try:
            with open(target, 'rb') as f:
                header = f.read(20)
                magic = header[:4]
                if magic != TELLTALE_MAGIC:
                    result.errors.append(f'{os.path.basename(target)}: неверный magic')
                    return result

                version = struct.unpack_from('<I', header, 4)[0]
                if version > 2:
                    result.warnings.append(
                        f'Версия TTArch {version} — возможны неточности'
                    )

                obj_offset = struct.unpack_from('<I', header, 8)[0]
                obj_count = struct.unpack_from('<I', header, 12)[0]
                flags = struct.unpack_from('<I', header, 16)[0] if len(header) >= 20 else 0

                if obj_count == 0:
                    result.warnings.append('Пустой архив (0 объектов)')
                    result.success = True
                    return result

                # Читаем таблицу объектов
                # Формат: на каждый объект — {compressed_size, uncomp_size, flags_or_hash, data_offset}
                # Размер записи может варьироваться между версиями
                obj_entry_size = 12  # compressed_size + uncomp_size + flags
                f.seek(obj_offset)
                obj_data = f.read(obj_count * obj_entry_size)

                entries = []
                for i in range(obj_count):
                    off = i * obj_entry_size
                    csize, usize = struct.unpack_from('<II', obj_data, off)
                    f2 = struct.unpack_from('<I', obj_data, off + 8)[0]
                    entries.append((csize, usize, f2))
        except (OSError, PermissionError) as e:
            result.errors.append(f'{os.path.basename(target)}: {e}')
            return result

        # Извлекаем объекты
        for idx, (csize, usize, file_flags) in enumerate(entries, 1):
            if csize == 0 and usize == 0:
                continue

            try:
                with open(target, 'rb') as f:
                    f.seek(obj_offset + obj_count * obj_entry_size + (
                        sum(e[0] for e in entries[:idx - 1])
                    ))
                    raw_data = f.read(csize)
            except (OSError, PermissionError) as e:
                result.errors.append(f'object_{idx}: ошибка чтения: {e}')
                continue

            name = f'object_{idx:04d}'
            ext = '.bin'
            if usize > 0 and csize != usize:
                ext = '.dmp'  # decompressed

            # Декомпрессия zlib если нужно
            if flags & 1 and csize != usize:
                try:
                    decompressed = zlib.decompress(raw_data)
                    if len(decompressed) == usize:
                        raw_data = decompressed
                        ext = ''
                except zlib.error:
                    pass  # возможно не сжато

            # Пытаемся определить расширение
            if len(raw_data) >= 8:
                if raw_data[:4] == b'\x89PNG':
                    ext = '.png'
                elif raw_data[:3] == b'\xff\xd8\xff':
                    ext = '.jpg'
                elif raw_data[:4] == b'DDS ':
                    ext = '.dds'
                elif raw_data[:4] == b'RIFF':
                    ext = '.wav'
                elif raw_data[:4] == b'OggS':
                    ext = '.ogg'

            safe_name = f'{name}{ext}'
            out_path = os.path.join(output_dir, safe_name)

            os.makedirs(output_dir, exist_ok=True)
            try:
                with open(out_path, 'wb') as f:
                    f.write(raw_data)
            except OSError as e:
                result.errors.append(f'{safe_name}: ошибка записи: {e}')
                if not options.continue_on_error:
                    return result
                continue

            result.files_extracted.append(out_path)

            if progress_callback:
                try:
                    progress_callback(safe_name, idx, len(entries))
                except Exception:
                    pass

        result.success = len(result.errors) == 0
        return result
