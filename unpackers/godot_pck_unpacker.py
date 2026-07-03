"""Unpacker для Godot Engine .pck архивов.

Формат (на основе Godot source: core/io/pck_packer.cpp, core/io/file_access_pack.cpp):
  Header (24 + 16 байт):
    Magic "GDPC" (4 байта)
    Version (uint32 LE): 1 или 2
    Godot Major (uint32 LE)
    Godot Minor (uint32 LE)
    Godot Patch/Revision (uint32 LE)
    Reserved 0x10 (4 байта) — v2: 0, v0/1: может быть флагом
    File base offset (uint32 LE)  — v2: 0, v1: 0, v0: 0x70+ (старый формат)
    Reserved 0x08 (4 байта)
    Reserved 0x0C (4 байта)
    Reserved 0x00 (4 байта, 16 total: 0x10 0x08 0x0C 0x00 = {16,8,12,0})

    После заголовка: 4 или 8 байт нулей (версионно-зависимо).
    Затем: uint32 — количество файлов.
    Затем: массив file entries начиная с file_base_offset.

  File Entry (v2):
    uint32 path_len
    char[path_len] path (UTF-8, без null-terminator)
    uint64 offset
    uint64 size
    uint8[16] md5 (может быть нулевым)
    uint32 flags (0=нет шифра, 1=AES-256 зашифрован если PCK зашифрован)

  File Entry (v1):
    uint32 path_len
    char[path_len] path
    uint32 offset
    uint32 size
    uint8[16] md5

Зашифрованные файлы (flags=1) не поддерживаются без ключа (как RPG Maker).
Без ключа файл сохраняется как .bin.
"""
from __future__ import annotations

import hashlib
import os
import struct
from typing import List, Optional

from core.base_unpacker import (
    BaseUnpacker, UnpackOptions, UnpackResult, ProgressCallback,
)

GODOT_PCK_MAGIC = b'GDPC'


class GodotPckUnpacker(BaseUnpacker):
    """Распаковщик Godot Engine .pck архивов."""

    name = 'godot_pck'

    @classmethod
    def detect(cls, target: str) -> bool:
        if not os.path.isfile(target):
            return False
        if not target.lower().endswith('.pck'):
            return False
        try:
            with open(target, 'rb') as f:
                head = f.read(4)
            if head == GODOT_PCK_MAGIC:
                return True

            # Некоторые PCK встроены в EXE — ищем с конца
            fz = os.path.getsize(target)
            if fz < 100:
                return False
            # Пропускаем embedded PCK в конце файла
            with open(target, 'rb') as f2:
                f2.seek(-len(GODOT_PCK_MAGIC), 2)
                tail = f2.read(4)
            return tail == GODOT_PCK_MAGIC
        except (OSError, PermissionError):
            return False

    def analyze(self, target: str) -> dict:
        info = {
            'type': 'godot_pck',
            'detected': self.detect(target),
            'file_size': os.path.getsize(target) if os.path.isfile(target) else 0,
            'error': None,
        }
        if not info['detected']:
            return info
        try:
            with open(target, 'rb') as f:
                magic = f.read(4)
                if magic != GODOT_PCK_MAGIC:
                    # Может быть EXE с embedded PCK в конце
                    fz = os.path.getsize(target)
                    f.seek(-4, 2)
                    tail = f.read(4)
                    if tail == GODOT_PCK_MAGIC:
                        info['embedded'] = True
                        # Ищем начало PCK — magic "GDPC" перед tail
                        # Поиск back-to-front
                        f.seek(0)
                        fdata = f.read()
                        pck_start = fdata.rfind(GODOT_PCK_MAGIC, 0, fz - 4)
                        if pck_start >= 0:
                            f_data = fdata[pck_start:]
                        else:
                            info['error'] = 'embedded PCK not found'
                            return info
                    else:
                        info['error'] = 'not a Godot PCK'
                        return info
                else:
                    f.seek(0)
                    f_data = f.read()

            # Читаем заголовок
            if len(f_data) < 24:
                info['error'] = 'header too short'
                return info
            version = struct.unpack_from('<I', f_data, 4)[0]
            major = struct.unpack_from('<I', f_data, 8)[0]
            minor = struct.unpack_from('<I', f_data, 12)[0]
            patch = struct.unpack_from('<I', f_data, 16)[0]
            info['version'] = version
            info['godot_ver'] = f'{major}.{minor}.{patch}'

            # Считаем файлы после reserved
            info['file_count'] = self._find_file_count(f_data, version)
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
                f'{os.path.basename(target)}: не Godot PCK (нет магии GDPC)'
            )
            return result

        output_dir = options.output_dir
        os.makedirs(output_dir, exist_ok=True)

        # Читаем весь файл
        try:
            with open(target, 'rb') as f:
                fz = os.path.getsize(target)
                magic = f.read(4)
                if magic != GODOT_PCK_MAGIC:
                    # Может быть EXE с embedded PCK
                    f.seek(0)
                    fdata = f.read()
                    pck_start = fdata.rfind(GODOT_PCK_MAGIC, 0, fz - 4)
                    if pck_start >= 0:
                        fdata = fdata[pck_start:]
                    else:
                        result.errors.append(
                            f'{os.path.basename(target)}: GDPC magic не найден'
                        )
                        return result
                else:
                    f.seek(0)
                    fdata = f.read()
        except (OSError, PermissionError) as e:
            result.errors.append(f'{os.path.basename(target)}: {e}')
            return result

        if len(fdata) < 24:
            result.errors.append(
                f'{os.path.basename(target)}: файл слишком короткий для PCK'
            )
            return result

        # Парсим заголовок
        version = struct.unpack_from('<I', fdata, 4)[0]
        if version not in (0, 1, 2):
            result.warnings.append(
                f'Неизвестная версия PCK {version} — обработка как v2'
            )

        # Ищем количество файлов
        magic = fdata[:4]
        pos = 20 if version == 1 else 24
        # Пропускаем reserved bytes
        if version >= 2:
            reserved = 16
        elif version == 1:
            reserved = 8
        else:
            reserved = 4

        # Читаем все поля reserved чтобы найти file_count
        # Формат: [magic 4] [version 4] [major 4] [minor 4] [patch 4]
        #         [reserved...] [file_count 4]
        # Reserved bytes (version >= 2): {0x10, 0x08, 0x0C, 0x00} × 4 байта каждый

        # Ищем file_count эвристически: после reserved ищем uint32 с разумным значением
        header_end = 24 + reserved
        file_count = 0
        count_offset = 0
        for off in range(header_end - 4, min(header_end + 8, len(fdata) - 8), 4):
            candidate = struct.unpack_from('<I', fdata, off)[0]
            if 1 <= candidate <= 100000:
                # Проверяем что следом идёт длина имени
                if off + 8 <= len(fdata):
                    name_len = struct.unpack_from('<I', fdata, off + 4)[0]
                    if 2 <= name_len <= 500:
                        file_count = candidate
                        count_offset = off + 4
                        break

        if file_count == 0:
            result.errors.append(
                f'{os.path.basename(target)}: не удалось найти список файлов '
                f'(версия PCK={version})'
            )
            return result

        # Читаем file entries
        entries = []
        pos = count_offset
        for i in range(file_count):
            if pos + 4 > len(fdata):
                break
            name_len = struct.unpack_from('<I', fdata, pos)[0]
            pos += 4
            if name_len == 0 or pos + name_len > len(fdata):
                result.warnings.append(
                    f'entry {i}: некорректная длина имени ({name_len})'
                )
                break
            name = fdata[pos:pos + name_len]
            try:
                name_str = name.decode('utf-8').rstrip('\x00')
            except UnicodeDecodeError:
                name_str = name.decode('utf-8', errors='replace').rstrip('\x00')
            pos += name_len

            if version >= 2 and pos + 16 > len(fdata):
                break
            if version < 2 and pos + 8 > len(fdata):
                break

            if version >= 2:
                offset = struct.unpack_from('<Q', fdata, pos)[0]
                size = struct.unpack_from('<Q', fdata, pos + 8)[0]
                md5 = fdata[pos + 16:pos + 32] if pos + 32 <= len(fdata) else b'\x00' * 16
                flags = struct.unpack_from('<I', fdata, pos + 32)[0] if pos + 36 <= len(fdata) else 0
                entry_size = 36  # 4 + path_len + 8 + 8 + 16 + 4
            else:
                offset = struct.unpack_from('<I', fdata, pos)[0]
                size = struct.unpack_from('<I', fdata, pos + 4)[0]
                md5 = fdata[pos + 8:pos + 24] if pos + 24 <= len(fdata) else b'\x00' * 16
                flags = 0
                entry_size = 24  # 4 + path_len + 4 + 4 + 16

            entries.append({
                'name': name_str,
                'offset': offset,
                'size': size,
                'md5': md5,
                'flags': flags,
            })
            pos += (entry_size - 4)  # path_len уже учтён, поэтому вычитаем 4

        if not entries:
            result.errors.append(
                f'{os.path.basename(target)}: не удалось прочитать записи о файлах'
            )
            return result

        # Извлекаем файлы
        for idx, entry in enumerate(entries, 1):
            name = entry['name']
            offset = entry['offset']
            size = entry['size']
            flags = entry['flags']
            expected_md5 = entry['md5']

            if size == 0:
                result.warnings.append(f'{name}: пустой файл (size=0)')
                continue

            # Зашифрованные файлы (flags=1)
            if flags & 1:
                result.warnings.append(
                    f'{name}: зашифрован (flags={flags}) — сохраняем как .enc'
                )
                # Читаем как есть
                if offset + size > len(fdata):
                    result.warnings.append(
                        f'{name}: offset+size за границами PCK'
                    )
                    continue
                data = fdata[offset:offset + size]
                safe_name = name.replace('\\', '/').replace('..', '_')
                out_path = os.path.join(
                    output_dir, f'{safe_name}.enc'
                )
                out_subdir = os.path.dirname(out_path)
                if out_subdir:
                    os.makedirs(out_subdir, exist_ok=True)
                with open(out_path, 'wb') as f:
                    f.write(data)
                result.files_extracted.append(out_path)
                continue

            if offset + size > len(fdata):
                result.warnings.append(
                    f'{name}: offset+size за границами PCK '
                    f'(offset={offset} size={size} pck_len={len(fdata)})'
                )
                continue

            data = fdata[offset:offset + size]

            # Проверяем MD5 если он не нулевой
            if expected_md5 and expected_md5 != b'\x00' * 16:
                actual_md5 = hashlib.md5(data).digest()
                if actual_md5 != expected_md5:
                    result.warnings.append(
                        f'{name}: MD5 не совпадает (файл может быть повреждён)'
                    )

            # Безопасный путь
            safe_parts = []
            for part in name.replace('\\', '/').split('/'):
                part = part.strip()
                if not part or part == '.':
                    continue
                if '..' in part:
                    result.skipped.append({
                        'path': name,
                        'reason': 'path traversal blocked',
                    })
                    continue
                safe_parts.append(part)

            if not safe_parts:
                safe_parts = [f'unnamed_{idx:04d}']

            out_path = os.path.join(output_dir, '/'.join(safe_parts))
            out_subdir = os.path.dirname(out_path)
            if out_subdir:
                os.makedirs(out_subdir, exist_ok=True)

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
                    progress_callback(name, idx, len(entries))
                except Exception:
                    pass

        result.success = len(result.errors) == 0
        return result

    @staticmethod
    def _find_file_count(fdata: bytes, version: int) -> int:
        """Эвристический поиск количества файлов в PCK заголовке."""
        # После 24-байтного базового заголовка идёт reserved.
        reserved = 16 if version >= 2 else (8 if version == 1 else 4)
        header_end = 24 + reserved

        for off in range(
            max(header_end - 4, 0),
            min(header_end + 8, len(fdata) - 8),
            4,
        ):
            candidate = struct.unpack_from('<I', fdata, off)[0]
            if 1 <= candidate <= 100000:
                name_len = struct.unpack_from('<I', fdata, off + 4)[0]
                if 2 <= name_len <= 500:
                    return candidate
        return 0
