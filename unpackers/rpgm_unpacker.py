"""Unpacker для RPG Maker MV/MZ/XP/VX/VX Ace архивов.

Поддерживает:
  - .rpgmvp / .png_ — encrypted PNG images (MV/MZ)
  - .rpgmvo / .ogg_ — encrypted OGG audio (MV/MZ)
  - .rpgmvm / .m4a_ — encrypted M4A audio (MV/MZ)
  - .rgssad — RPG Maker XP архив
  - .rgss2a — RPG Maker VX архив
  - .rgss3a — RPG Maker VX Ace архив
"""
from __future__ import annotations

import os
import sys
from typing import List, Optional, Tuple

from core.base_unpacker import (
    BaseUnpacker, UnpackOptions, UnpackResult, ProgressCallback,
)
from core.rpgm_decrypter import (
    RpgmDecrypter, RpgmDecryptError,
    find_rpg_maker_key, extract_key_from_rpgmvp,
)
from core.rpgm_reader import (
    detect_rgssad_variant, open_rgssad,
    RgssadError,
)
from unpackers.rpa_unpacker import (
    enable_long_path_support, to_extended_path,
    sanitize_filename, PathTraversalError,
)


# Расширения зашифрованных ресурсов MV/MZ и их оригинальные форматы
RPGMV_EXTENSIONS = {
    '.rpgmvp': '.png',  # PNG
    '.png_': '.png',
    '.rpgmvo': '.ogg',  # OGG
    '.ogg_': '.ogg',
    '.rpgmvm': '.m4a',  # M4A
    '.m4a_': '.m4a',
}


class RpgmUnpacker(BaseUnpacker):
    """Unpacker для RPG Maker MV/MZ (encrypted resources) и XP/VX/VX Ace (RGSSAD)."""
    name = 'rpgm'

    # Магические значения для детекции
    RPGMV_FAKE_HEADER = b'RPGMV'
    RGSS1A_MAGIC = b'RGSSAD'
    RGSS2A_MAGIC = b'RGSS2A'
    RGSS3A_MAGIC = b'RGSS3A'

    def __init__(self) -> None:
        super().__init__()
        self._decrypter: Optional[RpgmDecrypter] = None
        self._key_source: str = ''

    # ============ Detect / analyze ============

    def detect(self, target: str) -> bool:
        """Детектирует RPG Maker файл или папку."""
        if not os.path.exists(target):
            return False

        if os.path.isfile(target):
            ext = os.path.splitext(target)[1].lower()
            if ext in RPGMV_EXTENSIONS:
                return self._is_valid_encrypted(target)
            if ext in ('.rgssad', '.rgss2a', '.rgss3a'):
                return detect_rgssad_variant(target) is not None
            return False

        if os.path.isdir(target):
            return self._is_rpgm_dir(target)

        return False

    @classmethod
    def _is_valid_encrypted(cls, filepath: str) -> bool:
        """Проверяет, что файл — зашифрованный RPG Maker MV resource."""
        try:
            with open(filepath, 'rb') as f:
                head = f.read(8)
            return head.startswith(cls.RPGMV_FAKE_HEADER)
        except (OSError, PermissionError):
            return False

    @classmethod
    def _is_rpgm_dir(cls, folder: str) -> bool:
        """Проверяет, что папка содержит признаки RPG Maker игры."""
        for sys_path in ('www/data/System.json', 'data/System.json'):
            if os.path.isfile(os.path.join(folder, sys_path)):
                return True
        for root, _dirs, files in os.walk(folder):
            depth = root[len(folder):].count(os.sep)
            if depth > 2:
                continue
            for f in files:
                fl = f.lower()
                if fl.endswith(('.rgssad', '.rgss2a', '.rgss3a', '.rpgmvp', '.rpgmvo', '.rpgmvm')):
                    return True
        return False

    def analyze(self, target: str) -> dict:
        """Анализирует RPG Maker файл/папку, возвращает статистику."""
        info = {
            'type': 'unknown',
            'key_found': False,
            'key_source': '',
            'total_files': 0,
            'encrypted_files': 0,
            'raw_files': 0,
        }

        if os.path.isfile(target):
            ext = os.path.splitext(target)[1].lower()
            if ext in RPGMV_EXTENSIONS:
                info['type'] = 'rpgmv_encrypted_file'
                info['encrypted_files'] = 1
                if self._is_valid_encrypted(target):
                    key = extract_key_from_rpgmvp(target)
                    if key:
                        info['key_found'] = True
                        info['key_source'] = 'XOR analysis of rpgmvp header'
            elif ext in ('.rgssad', '.rgss2a', '.rgss3a'):
                variant = detect_rgssad_variant(target)
                info['type'] = variant or 'rgssad'
                try:
                    with open_rgssad(target) as r:
                        info['total_files'] = len(r.get_entries())
                except RgssadError:
                    pass
        elif os.path.isdir(target):
            info['type'] = 'rpgm_dir'
            key, src = find_rpg_maker_key(target)
            if key:
                info['key_found'] = True
                info['key_source'] = src
            for root, _dirs, files in os.walk(target):
                for f in files:
                    fl = f.lower()
                    if fl.endswith(tuple(RPGMV_EXTENSIONS.keys())):
                        info['encrypted_files'] += 1
                    else:
                        info['raw_files'] += 1
            info['total_files'] = info['encrypted_files'] + info['raw_files']

        return info

    # ============ Unpack ============

    def unpack(
        self,
        target: str,
        options: UnpackOptions,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> UnpackResult:
        """Распаковывает RPG Maker архив или папку."""
        result = UnpackResult(success=True, output_dir=options.output_dir)

        if options.use_long_paths:
            enable_long_path_support()

        output_dir = os.path.abspath(options.output_dir)

        if not os.path.exists(target):
            result.errors.append(f'Not found: {target}')
            result.success = False
            return result

        if os.path.isfile(target):
            self._unpack_file(target, output_dir, options, result, progress_callback)
        else:
            self._unpack_dir(target, output_dir, options, result, progress_callback)

        result.success = len(result.errors) == 0
        return result

    def _unpack_file(
        self,
        target: str,
        output_dir: str,
        options: UnpackOptions,
        result: UnpackResult,
        progress_callback: Optional[ProgressCallback],
    ) -> None:
        """Распаковывает один файл (RGSSAD или RPGMV encrypted)."""
        ext = os.path.splitext(target)[1].lower()
        if ext in RPGMV_EXTENSIONS:
            self._unpack_encrypted_file(target, output_dir, options, result, progress_callback)
        elif ext in ('.rgssad', '.rgss2a', '.rgss3a'):
            self._unpack_rgssad(target, output_dir, options, result, progress_callback)

    def _unpack_encrypted_file(
        self,
        target: str,
        output_dir: str,
        options: UnpackOptions,
        result: UnpackResult,
        progress_callback: Optional[ProgressCallback],
    ) -> None:
        """Дешифрует один .rpgmvp/.rpgmvo/.rpgmvm/.png_/.ogg_/.m4a_ файл."""
        ext = os.path.splitext(target)[1].lower()
        target_ext = RPGMV_EXTENSIONS.get(ext, '.bin')

        # 1) Попытка: ключ из соседней папки
        game_dir = self._find_game_dir(target)
        key, key_src = (None, '')
        if game_dir:
            key, key_src = find_rpg_maker_key(game_dir)

        # 2) Попытка: извлечь ключ из самого файла (XOR-анализ)
        if not key:
            key = extract_key_from_rpgmvp(target)
            if key:
                key_src = 'XOR analysis of file header'

        basename = os.path.basename(target)
        try:
            with open(target, 'rb') as f:
                data = f.read()

            if key:
                dec = RpgmDecrypter(encryption_key=key)
                self._decrypter = dec
                self._key_source = key_src
                decrypted = dec.decrypt(data)
                out_name = os.path.splitext(basename)[0] + target_ext
                self._write_data(output_dir, out_name, decrypted, options, result)
            else:
                # No key — пробуем no-key PNG recovery
                if ext in ('.rpgmvp', '.png_'):
                    dec = RpgmDecrypter(encryption_key=None)
                    try:
                        recovered = dec.restore_png_no_key(data)
                        out_name = os.path.splitext(basename)[0] + '.png'
                        self._write_data(output_dir, out_name, recovered, options, result)
                        result.skipped.append({
                            'path': basename,
                            'reason': 'png_recovered_no_key',
                        })
                        return
                    except RpgmDecryptError as e:
                        result.errors.append(f'{basename}: recovery failed: {e}')
                        return
                else:
                    result.errors.append(
                        f'{basename}: encryption key not found '
                        f'(put System.json or rpg_core.js near the file)'
                    )
                    return
        except RpgmDecryptError as e:
            result.errors.append(f'{basename}: {e}')
        except OSError as e:
            result.errors.append(f'{basename}: {e}')
        finally:
            if progress_callback:
                try:
                    progress_callback(basename, 1, 1)
                except Exception:
                    pass

    def _unpack_rgssad(
        self,
        target: str,
        output_dir: str,
        options: UnpackOptions,
        result: UnpackResult,
        progress_callback: Optional[ProgressCallback],
    ) -> None:
        """Распаковывает .rgssad/.rgss2a/.rgss3a архив."""
        basename = os.path.basename(target)
        try:
            with open_rgssad(target) as reader:
                entries = reader.get_entries()
                total = len(entries)
                for i, entry in enumerate(entries):
                    try:
                        data = reader.read_file_data(entry)
                        self._write_data(output_dir, entry.path, data, options, result)
                    except (RgssadError, OSError) as e:
                        result.errors.append(f'{entry.path}: {e}')
                    if progress_callback:
                        try:
                            progress_callback(entry.path, i + 1, total)
                        except Exception:
                            pass
        except RgssadError as e:
            result.errors.append(f'{basename}: {e}')

    def _unpack_dir(
        self,
        target: str,
        output_dir: str,
        options: UnpackOptions,
        result: UnpackResult,
        progress_callback: Optional[ProgressCallback],
    ) -> None:
        """Распаковывает папку RPG Maker игры (MV/MZ)."""
        # 1) Ищем ключ
        key, key_src = find_rpg_maker_key(target)
        if key:
            self._decrypter = RpgmDecrypter(encryption_key=key)
            self._key_source = key_src
        else:
            self._decrypter = None

        # 2) Собираем файлы для обработки
        tasks: List[Tuple[str, str]] = []  # (full_path, ext)
        for root, _dirs, files in os.walk(target):
            depth = root[len(target):].count(os.sep)
            if depth > 5:
                continue
            for f in files:
                fl = f.lower()
                if fl in RPGMV_EXTENSIONS or fl.endswith(tuple(RPGMV_EXTENSIONS.keys())):
                    full = os.path.join(root, f)
                    ext = os.path.splitext(fl)[1]
                    tasks.append((full, ext))

        total = len(tasks)
        for i, (full, ext) in enumerate(tasks):
            rel = os.path.relpath(full, target)
            try:
                with open(full, 'rb') as f:
                    data = f.read()
                if self._decrypter:
                    try:
                        decrypted = self._decrypter.decrypt(data)
                        target_ext = RPGMV_EXTENSIONS.get(ext, '.bin')
                    except RpgmDecryptError as e:
                        result.errors.append(f'{rel}: decrypt failed: {e}')
                        continue
                else:
                    if ext in ('.rpgmvp', '.png_'):
                        try:
                            decrypted = RpgmDecrypter().restore_png_no_key(data)
                            target_ext = '.png'
                            result.skipped.append({
                                'path': rel,
                                'reason': 'png_recovered_no_key',
                            })
                        except RpgmDecryptError as e:
                            result.errors.append(f'{rel}: recovery failed: {e}')
                            continue
                    else:
                        result.errors.append(f'{rel}: encryption key not found')
                        continue
                out_name = os.path.splitext(rel)[0].replace('\\', '/') + target_ext
                self._write_data(output_dir, out_name, decrypted, options, result)
            except OSError as e:
                result.errors.append(f'{rel}: {e}')

            if progress_callback:
                try:
                    progress_callback(rel, i + 1, total)
                except Exception:
                    pass

    # ============ Helpers ============

    def _find_game_dir(self, filepath: str) -> Optional[str]:
        """Поднимается по дереву папок и ищет System.json или rpg_core.js."""
        cur = os.path.dirname(os.path.abspath(filepath))
        for _ in range(5):
            if self._is_rpgm_dir(cur):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        return None

    def _write_data(
        self,
        output_dir: str,
        rel_path: str,
        data: bytes,
        options: UnpackOptions,
        result: UnpackResult,
    ) -> None:
        """Безопасно пишет data в output_dir с санитизацией."""
        try:
            safe_rel = self._safe_join(rel_path, output_dir, options.sanitize_names)
        except PathTraversalError as e:
            result.skipped.append({'path': rel_path, 'reason': f'path_traversal: {e}'})
            if not options.continue_on_error:
                result.errors.append(f'Path traversal: {rel_path}')
            return

        out_abs = os.path.join(output_dir, safe_rel.replace('/', os.sep))
        if options.use_long_paths and sys.platform == 'win32':
            write_path = to_extended_path(out_abs)
        else:
            write_path = out_abs

        try:
            os.makedirs(os.path.dirname(out_abs), exist_ok=True)
            if os.path.exists(out_abs) and not options.overwrite:
                result.skipped.append({'path': safe_rel, 'reason': 'exists'})
                return
            with open(write_path, 'wb') as f:
                f.write(data)
            result.files_extracted.append(safe_rel)
        except (OSError, PermissionError) as e:
            result.errors.append(f'{safe_rel}: {e}')

    def _safe_join(self, entry_path: str, output_dir: str, sanitize: bool) -> str:
        """Проверяет entry_path на безопасность и нормализует."""
        if os.path.isabs(entry_path) or entry_path.startswith('/') or entry_path.startswith('\\'):
            raise PathTraversalError(f'Absolute path in archive: {entry_path}')
        if ':' in entry_path[:3]:
            raise PathTraversalError(f'Absolute path in archive: {entry_path}')

        norm_path = entry_path.replace('\\', '/')
        if '..' in norm_path.split('/'):
            raise PathTraversalError(f'Path traversal attempt: {entry_path}')

        parts = norm_path.split('/')
        safe_parts = []
        for part in parts:
            if not part or part == '.':
                continue
            if part == '..':
                raise PathTraversalError(f'Path traversal attempt: {entry_path}')
            if ':' in part or '\\' in part:
                raise PathTraversalError(f'Invalid path component: {part}')
            if sanitize:
                part = sanitize_filename(part)
            safe_parts.append(part)

        if not safe_parts:
            raise PathTraversalError(f'Empty path in archive: {entry_path}')

        safe_rel = '/'.join(safe_parts)
        safe_abs = os.path.abspath(os.path.join(output_dir, safe_rel))
        output_abs = os.path.abspath(output_dir)
        if not safe_abs.startswith(output_abs + os.sep) and safe_abs != output_abs:
            raise PathTraversalError(f'Path traversal attempt: {entry_path}')

        return safe_rel
