"""Unpacker для Unreal Engine .pak архивов через pyuepak.

Использует библиотеку pyuepak для полноценной распаковки:
- Поддержка версий 1-12
- Zlib / Gzip / Oodle / LZ4 сжатие
- AES-256 шифрование (с ключом)
- Mount point и path hash seed
"""
from __future__ import annotations

import os
import struct
import sys
import traceback
import ctypes
from typing import List, Optional

from core.base_unpacker import (
    BaseUnpacker, UnpackOptions, UnpackResult, ProgressCallback,
)
from unpackers.rpa_unpacker import sanitize_filename, PathTraversalError


UNREAL_PAK_MAGIC = b'PAK\x00'
UNREAL_PAK_FOOTER_MAGIC = 0x5A6F12E1
UNREAL_PAK_FOOTER_OFFSETS = (44, 172, 204, 205)
UNREAL_PAK_ZERO_GUID = '0' * 32
UNREAL_PAK_FOOTER_LAYOUTS = (
    {'footer_size': 44, 'guid_size': 0, 'has_encryption_flag': False, 'version_mode': 'direct'},
    {'footer_size': 45, 'guid_size': 0, 'has_encryption_flag': True, 'version_mode': 'direct'},
    {'footer_size': 61, 'guid_size': 16, 'has_encryption_flag': True, 'version_mode': 'direct'},
    {'footer_size': 189, 'guid_size': 16, 'has_encryption_flag': True, 'version_mode': 'fixed', 'version_value': '8A'},
    {'footer_size': 221, 'guid_size': 16, 'has_encryption_flag': True, 'version_mode': 'plus_one'},
    {'footer_size': 222, 'guid_size': 16, 'has_encryption_flag': True, 'version_mode': 'fixed', 'version_value': 9},
)


def has_unreal_pak_signature(target: str) -> bool:
    """Проверяет сигнатуры Unreal PAK в начале файла и в footer.

    Многие реальные UE4/UE5 `.pak` хранят магию не в первых 4 байтах, а в
    footer рядом с метаданными индекса. Для детекта нам достаточно увидеть
    одну из известных footer-позиций, которые использует pyuepak.
    """
    if not os.path.isfile(target):
        return False
    if not target.lower().endswith('.pak'):
        return False

    try:
        size = os.path.getsize(target)
        with open(target, 'rb') as f:
            if f.read(4) == UNREAL_PAK_MAGIC:
                return True

            for footer_size in UNREAL_PAK_FOOTER_OFFSETS:
                if size < footer_size:
                    continue
                f.seek(-footer_size, os.SEEK_END)
                magic = struct.unpack('<I', f.read(4))[0]
                if magic == UNREAL_PAK_FOOTER_MAGIC:
                    return True
    except (OSError, PermissionError, struct.error):
        return False

    return False


def normalize_unreal_aes_key(value: Optional[str]) -> Optional[str]:
    """Нормализует AES-ключ Unreal `.pak` к виду `0x...`.

    Поддерживается hex-строка длиной 64 символа (32 байта), с префиксом
    `0x` или без него.
    """
    if value is None:
        return None

    text = value.strip().strip('"').strip("'")
    if not text:
        return None

    if text.lower().startswith('0x'):
        text = text[2:]

    try:
        raw = bytes.fromhex(text)
    except ValueError as e:
        raise ValueError('AES-ключ Unreal должен быть hex-строкой') from e

    if len(raw) != 32:
        raise ValueError(
            f'AES-ключ Unreal должен быть длиной 32 байта (сейчас {len(raw)})'
        )

    return '0x' + text.upper()


def get_unreal_pak_encryption_info(target: str) -> dict:
    """Возвращает сведения о footer Unreal `.pak`, включая encryption flag."""
    info = {
        'detected': False,
        'version': None,
        'is_encrypted_index': False,
        'encryption_guid': '',
        'footer_size': None,
        'note': '',
    }

    if not os.path.isfile(target):
        info['note'] = 'Файл не найден'
        return info
    if not target.lower().endswith('.pak'):
        info['note'] = 'Расширение не .pak'
        return info

    try:
        size = os.path.getsize(target)
        with open(target, 'rb') as f:
            if f.read(4) == UNREAL_PAK_MAGIC:
                info['detected'] = True

            for layout in UNREAL_PAK_FOOTER_LAYOUTS:
                footer_size = layout['footer_size']
                if size < footer_size:
                    continue

                footer_start = size - footer_size
                magic_offset = footer_start + layout['guid_size']
                if layout['has_encryption_flag']:
                    magic_offset += 1

                f.seek(magic_offset)
                magic = struct.unpack('<I', f.read(4))[0]
                if magic != UNREAL_PAK_FOOTER_MAGIC:
                    continue

                version_raw = struct.unpack('<I', f.read(4))[0]
                version_mode = layout['version_mode']
                if version_mode == 'direct':
                    version = version_raw
                elif version_mode == 'plus_one':
                    version = version_raw + 1
                else:
                    version = layout['version_value']

                encryption_guid = ''
                if layout['guid_size']:
                    f.seek(footer_start)
                    encryption_guid = f.read(layout['guid_size']).hex()

                is_encrypted_index = False
                if layout['has_encryption_flag']:
                    f.seek(footer_start + layout['guid_size'])
                    is_encrypted_index = f.read(1) == b'\x01'

                info.update({
                    'detected': True,
                    'version': version,
                    'is_encrypted_index': is_encrypted_index,
                    'encryption_guid': (
                        '' if encryption_guid == UNREAL_PAK_ZERO_GUID
                        else encryption_guid
                    ),
                    'footer_size': footer_size,
                    'note': '',
                })
                return info
    except (OSError, PermissionError, struct.error) as e:
        info['note'] = f'{type(e).__name__}: {e}'
        return info

    if info['detected']:
        info['note'] = 'Не удалось распознать footer Unreal .pak'
    else:
        info['note'] = 'Сигнатура Unreal .pak не найдена'
    return info


def _check_pyuepak():
    """Ленивый импорт pyuepak с понятной ошибкой."""
    try:
        from pyuepak import PakFile  # noqa: F401
        _patch_pyuepak_oodle()
        return True
    except ImportError as e:
        raise RuntimeError(
            'pyuepak не установлен. Установите: pip install pyuepak'
        ) from e


def _patch_pyuepak_oodle() -> None:
    """Исправляет передачу Oodle-буфера в ctypes для pyuepak.

    В pyuepak 0.2.8 входной буфер передаётся в `OodleLZ_Decompress` как
    обычный `bytes`, из-за чего на части Oodle-сжатых `.pak` возникает
    `ctypes.ArgumentError`. Передаём данные как явный C-буфер.
    """
    try:
        import pyuepak.oodle as oodle_mod
        from pyuepak.oodle import CompressionFailed
    except ImportError:
        return

    if getattr(oodle_mod.Oodle.decompress, '_gaextractor_patched', False):
        return

    def _fixed_decompress(self, data: bytes, output_size: int) -> bytes:
        raw = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        out_buffer = (ctypes.c_ubyte * output_size)()
        written = self.decompress_fn(
            raw,
            len(data),
            out_buffer,
            output_size,
            1,
            1,
            0,
            None,
            0,
            None,
            None,
            None,
            0,
            3,
        )
        if written <= 0:
            raise CompressionFailed('Oodle decompression failed')
        return bytes(out_buffer[:written])

    _fixed_decompress._gaextractor_patched = True
    oodle_mod.Oodle.decompress = _fixed_decompress


class UnrealPakUnpacker(BaseUnpacker):
    """Unpacker для Unreal Engine .pak архивов."""

    name = 'pak'

    @classmethod
    def detect(cls, target: str) -> bool:
        """Проверяет что файл — это .pak архив Unreal Engine."""
        return has_unreal_pak_signature(target)

    def analyze(self, target: str) -> dict:
        """Анализирует .pak файл и возвращает статистику."""
        info = get_unreal_pak_encryption_info(target)
        info.update({
            'type': 'unreal_pak',
            'file_size': os.path.getsize(target) if os.path.isfile(target) else 0,
        })
        if not info['detected']:
            return info
        try:
            _check_pyuepak()
            from pyuepak import PakFile
            pak = PakFile()
            pak.read(target)
            info['version'] = int(pak.version)
            info['file_count'] = pak.count
            info['mount_point'] = pak.mount_point
            files = pak.list_files()
            info['sample_files'] = files[:10]
            if len(files) > 10:
                info['sample_files'].append(f'... (+{len(files) - 10} more)')
        except Exception as e:
            if not info.get('note'):
                info['note'] = f'Ошибка чтения индекса: {type(e).__name__}: {e}'
        return info

    def unpack(
        self,
        target: str,
        options: UnpackOptions,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> UnpackResult:
        """Распаковывает .pak архив в options.output_dir."""
        result = UnpackResult(success=False, output_dir=options.output_dir)

        if not self.detect(target):
            result.errors.append(
                f'{os.path.basename(target)}: не похоже на .pak (нет магии PAK\\0)'
            )
            return result

        _check_pyuepak()

        output_dir = options.output_dir
        try:
            aes_key = normalize_unreal_aes_key(options.unreal_aes_key)
        except ValueError as e:
            result.errors.append(str(e))
            return result

        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            result.errors.append(f'Не удалось создать {output_dir}: {e}')
            return result

        # Читаем pak-файл
        try:
            from pyuepak import PakFile
            pak = PakFile()
            if aes_key:
                pak.set_key(aes_key)
            pak.read(target)
        except Exception as e:
            if 'Encryption key is required' in str(e) and not aes_key:
                enc_info = get_unreal_pak_encryption_info(target)
                guid_hint = ''
                if enc_info.get('encryption_guid'):
                    guid_hint = (
                        f' GUID: {enc_info["encryption_guid"]}. '
                        'Это не сам AES-ключ, а идентификатор.'
                    )
                result.errors.append(
                    'Требуется AES-ключ Unreal для зашифрованного .pak индекса.'
                    + guid_hint
                )
                return result
            result.errors.append(
                f'{os.path.basename(target)}: ошибка чтения индекса: '
                f'{type(e).__name__}: {e}'
            )
            return result

        file_list = pak.list_files()
        total = len(file_list)
        if total == 0:
            result.warnings.append(
                f'{os.path.basename(target)}: пустой архив (0 файлов)'
            )
            result.success = True
            return result

        # Определяем общий префикс (mount point) чтобы не дублировать
        mount_point = (pak.mount_point or '').rstrip('/').rstrip('\\')

        for idx, file_path in enumerate(file_list, 1):
            try:
                # Вычисляем относительный путь
                rel = file_path.lstrip('/').lstrip('\\')
                if mount_point and rel.lower().startswith(
                    mount_point.lower().lstrip('/').lstrip('\\') + '/'
                ):
                    rel = rel[len(mount_point) + 1:]

                # Sanitize путь
                try:
                    safe_parts = sanitize_filename(rel)
                except PathTraversalError:
                    # Пропускаем небезопасные пути
                    result.skipped.append({
                        'path': file_path,
                        'reason': 'unsafe path (path traversal blocked)',
                    })
                    continue

                out_path = os.path.join(output_dir, safe_parts.replace('/', os.sep))

                # Создаём подпапки
                out_subdir = os.path.dirname(out_path)
                if out_subdir:
                    try:
                        os.makedirs(out_subdir, exist_ok=True)
                    except OSError as e:
                        result.warnings.append(
                            f'{file_path}: не удалось создать папку: {e}'
                        )
                        continue

                # Читаем данные файла
                try:
                    data = pak.read_file(file_path)
                except Exception as e:
                    result.warnings.append(
                        f'{file_path}: ошибка чтения: {type(e).__name__}: {e}'
                    )
                    if not options.continue_on_error:
                        result.errors.append(
                            f'{file_path}: {type(e).__name__}: {e}'
                        )
                        return result
                    continue

                if data is None:
                    result.warnings.append(f'{file_path}: пустые данные')
                    continue

                # Сохраняем
                try:
                    with open(out_path, 'wb') as f:
                        f.write(data)
                except OSError as e:
                    result.errors.append(f'{file_path}: ошибка записи: {e}')
                    if not options.continue_on_error:
                        return result
                    continue

                result.files_extracted.append(out_path)

                if progress_callback:
                    try:
                        progress_callback(file_path, idx, total)
                    except Exception:
                        pass

            except Exception as e:
                result.errors.append(
                    f'{file_path}: неожиданная ошибка: {type(e).__name__}: {e}'
                )
                if not options.continue_on_error:
                    return result

        result.success = len(result.errors) == 0
        return result
