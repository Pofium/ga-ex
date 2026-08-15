"""Unpacker для Godot Engine .pck архивов.

Формат (на основе Godot source: core/io/pck_packer.cpp, core/io/file_access_pack.cpp):

  Header (для всех версий):
    Magic "GDPC" (4 байта)
    Pack version (uint32 LE): 0/1 (Godot 3.x), 2 (Godot 4.0–4.3), 3 (Godot 4.4+)
    Godot Major (uint32 LE)
    Godot Minor (uint32 LE)
    Godot Patch (uint32 LE)
    --- v2/v3 (Godot 4): ---
    Pack flags (uint32):   bit0=PACK_DIR_ENCRYPTED, bit1=PACK_REL_FILEBASE
    File base offset (uint64): база для offset-ов файлов (обычно = конец заголовка)
    Directory offset (uint64): смещение таблицы файлов (в конце PCK!)
    --- v0/v1 (Godot 3): ---
    reserved 16 байт (16×uint32)
    Таблица файлов идёт СРАЗУ после заголовка.

  Таблица файлов (по смещению dir_offset для v2/v3, или сразу после заголовка для v0/v1):
    uint32 file_count
    file_count × entry:
      uint32 path_len
      char[path_len] path (UTF-8, без null-terminator)
      uint64 offset   (относительно file_base; для v0/v1 — относительно начала файла)
      uint64 size
      uint8[16] md5 (может быть нулевым)
      uint32 flags (только v2/v3; bit0=PACK_FILE_ENCRYPTED)

Зашифрованные файлы (flags & 1) сохраняются как есть (без дешифровки — нет ключа).
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

# Pack flags (Godot 4)
PACK_DIR_ENCRYPTED = 1
PACK_REL_FILEBASE = 2
# File flags
PACK_FILE_ENCRYPTED = 1


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

    @staticmethod
    def _locate_pck_start(fdata: bytes) -> int:
        """Возвращает смещение начала PCK (для встроенного в EXE — ищет magic)."""
        if fdata[:4] == GODOT_PCK_MAGIC:
            return 0
        idx = fdata.rfind(GODOT_PCK_MAGIC)
        return idx if idx >= 0 else -1

    @classmethod
    def _parse_header(cls, fdata: bytes, base: int) -> Optional[dict]:
        """Парсит заголовок PCK. Возвращает dict или None при ошибке.

        Для Godot 4 (pack v2/v3) возвращает file_base, dir_offset, flags.
        Для Godot 3 (pack v0/v1) dir_offset = None (таблица сразу после заголовка).
        """
        if base + 20 > len(fdata):
            return None
        magic = fdata[base:base + 4]
        if magic != GODOT_PCK_MAGIC:
            return None
        pack_ver = struct.unpack_from('<I', fdata, base + 4)[0]
        major = struct.unpack_from('<I', fdata, base + 8)[0]
        minor = struct.unpack_from('<I', fdata, base + 12)[0]
        patch = struct.unpack_from('<I', fdata, base + 16)[0]

        info = {
            'pack_ver': pack_ver,
            'godot_ver': f'{major}.{minor}.{patch}',
            'flags': 0,
            'file_base': 0,
            'dir_offset': None,  # None = таблица сразу после заголовка
            'header_size': 20,
        }

        if pack_ver >= 2:
            # Godot 4: flags(uint32) + file_base(uint64) + dir_offset(uint64)
            if base + 40 > len(fdata):
                return None
            info['flags'] = struct.unpack_from('<I', fdata, base + 20)[0]
            info['file_base'] = struct.unpack_from('<Q', fdata, base + 24)[0]
            info['dir_offset'] = struct.unpack_from('<Q', fdata, base + 32)[0]
            info['header_size'] = 40
            # PACK_REL_FILEBASE всегда включён в v3; файлы отсчитываются от file_base
            if pack_ver >= 3 or (info['flags'] & PACK_REL_FILEBASE):
                pass  # offset-ы уже относительны file_base
            else:
                # v2 без PACK_REL_FILEBASE — offset-ы абсолютные (file_base=0)
                info['file_base'] = 0
        else:
            # Godot 3 (pack v0/v1): 16 reserved байт после версии
            info['header_size'] = 20 + 16  # 36
        return info

    @classmethod
    def _read_file_table(cls, fdata: bytes, header: dict, base: int) -> List[dict]:
        """Читает таблицу файлов по dir_offset (или после заголовка)."""
        dir_off = header['dir_offset']
        if dir_off is None:
            # Godot 3: таблица сразу после заголовка (относительно base)
            pos = base + header['header_size']
        else:
            # Godot 4: абсолютное смещение директории
            pos = dir_off
            # Для встроенного PCK dir_offset абсолютный от начала файла

        if pos + 4 > len(fdata):
            return []
        file_count = struct.unpack_from('<I', fdata, pos)[0]
        pos += 4
        if file_count > 1000000:  # sanity
            return []

        entries: List[dict] = []
        pack_ver = header['pack_ver']
        for i in range(file_count):
            if pos + 4 > len(fdata):
                break
            name_len = struct.unpack_from('<I', fdata, pos)[0]
            pos += 4
            if name_len == 0 or name_len > 65535 or pos + name_len > len(fdata):
                break
            raw = fdata[pos:pos + name_len]
            try:
                name = raw.decode('utf-8').rstrip('\x00')
            except UnicodeDecodeError:
                name = raw.decode('utf-8', errors='replace').rstrip('\x00')
            pos += name_len

            if pack_ver >= 2:
                # uint64 offset, uint64 size, md5[16], uint32 flags
                if pos + 36 > len(fdata):
                    break
                offset = struct.unpack_from('<Q', fdata, pos)[0]
                size = struct.unpack_from('<Q', fdata, pos + 8)[0]
                md5 = fdata[pos + 16:pos + 32]
                flags = struct.unpack_from('<I', fdata, pos + 32)[0]
                pos += 36
            else:
                # Godot 3 v0/v1: uint32 offset, uint32 size, md5[16]
                if pos + 24 > len(fdata):
                    break
                offset = struct.unpack_from('<I', fdata, pos)[0]
                size = struct.unpack_from('<I', fdata, pos + 4)[0]
                md5 = fdata[pos + 8:pos + 24]
                flags = 0
                pos += 24

            entries.append({
                'name': name,
                'offset': offset,
                'size': size,
                'md5': md5,
                'flags': flags,
            })
        return entries

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
                fdata = f.read()
            base = self._locate_pck_start(fdata)
            if base < 0:
                info['error'] = 'GDPC magic not found'
                return info
            if base > 0:
                info['embedded'] = True
            header = self._parse_header(fdata, base)
            if header is None:
                info['error'] = 'header too short / invalid'
                return info
            info['version'] = header['pack_ver']
            info['godot_ver'] = header['godot_ver']
            info['flags'] = header['flags']
            entries = self._read_file_table(fdata, header, base)
            info['file_count'] = len(entries)
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

        # Читаем весь файл (PCK или EXE со встроенным PCK)
        try:
            with open(target, 'rb') as f:
                fdata = f.read()
        except (OSError, PermissionError) as e:
            result.errors.append(f'{os.path.basename(target)}: {e}')
            return result

        if len(fdata) < 24:
            result.errors.append(
                f'{os.path.basename(target)}: файл слишком короткий для PCK'
            )
            return result

        # Локализуем начало PCK (для встроенного в EXE)
        base = self._locate_pck_start(fdata)
        if base < 0:
            result.errors.append(
                f'{os.path.basename(target)}: GDPC magic не найден'
            )
            return result

        header = self._parse_header(fdata, base)
        if header is None:
            result.errors.append(
                f'{os.path.basename(target)}: некорректный заголовок PCK'
            )
            return result

        pack_ver = header['pack_ver']
        if pack_ver not in (0, 1, 2, 3):
            result.warnings.append(
                f'Неизвестная версия PCK {pack_ver} — попытка обработки как v2'
            )

        # Зашифрованная директория (PACK_DIR_ENCRYPTED) — не читается без ключа
        if header['flags'] & PACK_DIR_ENCRYPTED:
            result.errors.append(
                f'{os.path.basename(target)}: таблица файлов зашифрована '
                f'(PACK_DIR_ENCRYPTED) — требуется ключ шифрования PCK'
            )
            return result

        entries = self._read_file_table(fdata, header, base)
        if not entries:
            result.errors.append(
                f'{os.path.basename(target)}: не удалось прочитать записи о файлах '
                f'(версия PCK={pack_ver})'
            )
            return result

        # База для offset-ов: для Godot 4 — file_base (абсолютный от начала файла,
        # даже если PCK встроен в EXE и base>0 — Godot пишет абсолютные смещения).
        # Для Godot 3 offset-ы уже абсолютные от начала PCK.
        file_base = header['file_base'] if pack_ver >= 2 else 0
        # Для встроенного PCK нужно скорректировать на base только в случае Godot 3,
        # где offset-ы относительны начала PCK (а не файла).
        if pack_ver < 2 and base > 0:
            file_base = base

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

            # Зашифрованные файлы (flags & PACK_FILE_ENCRYPTED) сохраняем как есть.
            if flags & PACK_FILE_ENCRYPTED:
                result.warnings.append(
                    f'{name}: зашифрован (flags={flags}) — сохраняем как .enc'
                )
                # Читаем как есть
                abs_off = file_base + offset
                if abs_off + size > len(fdata):
                    result.warnings.append(
                        f'{name}: offset+size за границами PCK'
                    )
                    continue
                data = fdata[abs_off:abs_off + size]
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

            abs_off = file_base + offset
            if abs_off + size > len(fdata):
                result.warnings.append(
                    f'{name}: offset+size за границами PCK '
                    f'(offset={abs_off} size={size} pck_len={len(fdata)})'
                )
                continue

            data = fdata[abs_off:abs_off + size]

            # Проверяем MD5 если он не нулевой
            if expected_md5 and expected_md5 != b'\x00' * 16:
                actual_md5 = hashlib.md5(data).digest()
                if actual_md5 != expected_md5:
                    result.warnings.append(
                        f'{name}: MD5 не совпадает (файл может быть повреждён)'
                    )

            # Безопасный путь. Godot хранит пути с префиксами res://, user://,
            # uid:// — обрезаем их, чтобы получить чистую файловую иерархию.
            clean_name = name.replace('\\', '/')
            for prefix in ('res://', 'user://', 'uid://', 'res:\\\\'):
                if clean_name.lower().startswith(prefix):
                    clean_name = clean_name[len(prefix):]
                    break

            safe_parts = []
            for part in clean_name.split('/'):
                part = part.strip()
                if not part or part == '.':
                    continue
                if part == '..':
                    result.skipped.append({
                        'path': name,
                        'reason': 'path traversal blocked',
                    })
                    continue
                # Заменяем недопустимые в именах файлов символы (:, *, ?, и т.д.)
                if options.sanitize_names:
                    part = self._sanitize_part(part)
                safe_parts.append(part)

            if not safe_parts:
                safe_parts = [f'unnamed_{idx:04d}']

            out_path = os.path.join(output_dir, *safe_parts)
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

            # Godot 4 хранит текстуры в формате .ctex (GST2): внутри лежит
            # обычное изображение (WebP/PNG/JPEG). Извлекаем его рядом как
            # удобный читаемый файл.
            if name.endswith('.ctex'):
                img_path = self._write_embedded_image(data, out_path)
                if img_path:
                    result.files_extracted.append(img_path)

            if progress_callback:
                try:
                    progress_callback(name, idx, len(entries))
                except Exception:
                    pass

        result.success = len(result.errors) == 0
        return result

    @staticmethod
    def _sanitize_part(part: str) -> str:
        """Заменяет символы, недопустимые в именах файлов, на '_'."""
        # Windows недопустимые: < > : " / \ | ? *  и управляющие символы
        bad = set('<>:"/\\|?*\x00')
        return ''.join('_' if (c in bad or ord(c) < 32) else c for c in part)

    @staticmethod
    def _write_embedded_image(ctex_data: bytes, ctex_path: str) -> Optional[str]:
        """Извлекает встроенное изображение из .ctex (GST2) и сохраняет рядом.

        Godot 4 StreamTexture2D (.ctex) содержит обычный WebP/PNG/JPEG по
        фиксированному смещению (обычно 56). Метод ищет известные сигнатуры
        изображения и сохраняет его как <имя>.<расширение> рядом с .ctex.
        Возвращает путь к созданному файлу или None.
        """
        # Сигнатуры: (needle, offset_adjust, extension)
        # RIFF....WEBP  — RIFF начинается за 8 байт до 'WEBP'
        candidates = []
        idx = ctex_data.find(b'WEBP')
        if idx >= 0 and idx >= 8 and ctex_data[idx - 8:idx - 4] == b'RIFF':
            candidates.append((idx - 8, '.webp', b'RIFF'))
        idx_png = ctex_data.find(b'\x89PNG\r\n\x1a\n')
        if idx_png >= 0:
            candidates.append((idx_png, '.png', b'\x89PNG'))
        idx_jpg = ctex_data.find(b'\xff\xd8\xff')
        if idx_jpg >= 0:
            candidates.append((idx_jpg, '.jpg', b'\xff\xd8\xff'))

        if not candidates:
            return None

        start, ext, sig = candidates[0]
        # Длина: для RIFF/WebP — из заголовка RIFF; для PNG — до IEND; для JPEG — до конца.
        payload = b''
        if ext == '.webp':
            if start + 8 > len(ctex_data):
                return None
            riff_size = struct.unpack_from('<I', ctex_data, start + 4)[0]
            end = start + 8 + riff_size
            if end > len(ctex_data):
                end = len(ctex_data)
            payload = ctex_data[start:end]
        elif ext == '.png':
            iend = ctex_data.find(b'IEND', start)
            if iend < 0:
                return None
            end = iend + 8  # IEND chunk: len(4)+type(4)+crc(4) — type найден, +4(crc)+4
            end = iend + 4 + 4  # 'IEND' + CRC
            payload = ctex_data[start:end]
        else:  # jpg — до конца (JPEG не имеет чёткого маркера длины)
            end = ctex_data.rfind(b'\xff\xd9')  # EOI marker
            if end < 0:
                end = len(ctex_data)
            else:
                end += 2
            payload = ctex_data[start:end]

        if not payload or not payload.startswith(sig):
            return None

        # Имя: берём basename .ctex без хеш-суффикса, добавляем расширение картинки.
        base_name = os.path.basename(ctex_path)
        # .ctex файлы имеют вид "<orig>.png-<hash>.ctex" — обрежем хеш
        if '-' in base_name and base_name.endswith('.ctex'):
            stem = base_name[:-len('.ctex')]
            dash = stem.rfind('-')
            # Хеш — 32 hex-символа после последнего '-'
            if dash > 0 and len(stem) - dash - 1 >= 32:
                stem = stem[:dash]
            base_name = stem
        else:
            base_name = base_name[:-len('.ctex')] if base_name.endswith('.ctex') else base_name

        out_dir = os.path.dirname(ctex_path)
        out_path = os.path.join(out_dir, base_name + ext)
        # Если уже есть (имя совпало) — добавляем индекс
        if os.path.exists(out_path):
            i = 1
            while os.path.exists(os.path.join(out_dir, f'{base_name}_{i}{ext}')):
                i += 1
            out_path = os.path.join(out_dir, f'{base_name}_{i}{ext}')

        try:
            with open(out_path, 'wb') as f:
                f.write(payload)
        except OSError:
            return None
        return out_path
