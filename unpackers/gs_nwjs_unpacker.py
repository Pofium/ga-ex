"""Unpacker для игр на GS-движке поверх NW.js (House of Maids и др.).

GS-движок шифрует ресурсы простым XOR с фиксированным 5-байтным ключом,
применяемым циклически ко всему файлу. Источник ключа — класс
``GS.DataPreparer`` в ``data/ENGINE.js``: ``prepare()`` делает
``data[i] ^= key[i % key.length]`` при включённом ``$PARAMS.needsPreparation``,
а ``generateKey()`` строит ключ из seed ``Int32Array([42,11,23,88,133])``.

Зашифрованы медиа в ``resources/`` (PNG/JPG/OGG/WAV/WOFF/WebM) и игровые
скрипты в ``data/*.json.js``. Движковые ``data/lib/*.js`` лежат в открытом
виде. Данный распаковщик дешифрует зашифрованные файлы и сохраняет структуру
каталогов внутри папки назначения; открытые файлы движка не копируются.
"""
from __future__ import annotations

import os
import sys
from typing import List, Optional, Tuple

from core.base_unpacker import (
    BaseUnpacker, UnpackOptions, UnpackResult, ProgressCallback,
)
from core.detector import FormatDetector, GameFormat
from unpackers.rpa_unpacker import (
    enable_long_path_support, to_extended_path,
    sanitize_filename, PathTraversalError,
)


class GsNwjsUnpacker(BaseUnpacker):
    """Дешифрует ресурсы GS-движка (NW.js) с фиксированным XOR-ключом."""

    name = 'gs_nwjs'

    # 5-байтный XOR-ключ (дублируем из детектора для автономности модуля).
    KEY: bytes = FormatDetector.GS_NWJS_KEY
    # Сигнатуры медиа после дешифровки.
    SIGNATURES: Tuple[bytes, ...] = FormatDetector.GS_NWJS_SIGNATURES
    # Расширения медиа, которые GS-движок шифрует.
    MEDIA_EXTS: Tuple[str, ...] = FormatDetector.GS_MEDIA_EXTS

    # Каталоги/файлы движка и окружения NW.js, которые не нужно тащить в вывод.
    _SKIP_DIRS = {
        '__pycache__', '.git', 'node_modules', 'swiftshader', 'locales',
    }
    _SKIP_EXTS = {
        '.dll', '.exe', '.lib', '.dat', '.pak', '.bin', '.node', '.so',
        '.dylib', '.url',
    }

    # ============ Detect / analyze ============

    def detect(self, target: str) -> bool:
        """True, если target — папка GS-игры или зашифрованный GS-файл."""
        if not os.path.exists(target):
            return False
        if os.path.isdir(target):
            return FormatDetector.is_gs_nwjs_game_folder(target)
        if os.path.isfile(target):
            return FormatDetector.is_gs_nwjs_encrypted_file(target)
        return False

    def analyze(self, target: str) -> dict:
        """Возвращает статистику по зашифрованным ресурсам."""
        info: dict = {
            'type': 'gs_nwjs',
            'total_files': 0,
            'encrypted_files': 0,
            'media_files': 0,
            'script_files': 0,
        }
        if os.path.isfile(target):
            info['total_files'] = 1
            if self.detect(target):
                info['encrypted_files'] = 1
                if os.path.splitext(target)[1].lower() in self.MEDIA_EXTS:
                    info['media_files'] = 1
            return info
        if not os.path.isdir(target):
            return info

        info['type'] = 'gs_nwjs_folder'
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if d not in self._SKIP_DIRS]
            in_data = os.sep + 'data' + os.sep in (root + os.sep)
            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                full = os.path.join(root, fn)
                is_media = ext in self.MEDIA_EXTS and self._is_encrypted(full)
                # data/*.json.js и data/*.js — зашифрованные скрипты, кроме lib/
                in_lib = os.sep + 'data' + os.sep + 'lib' + os.sep in (root + os.sep)
                is_script = (in_data and not in_lib and ext == '.js'
                             and self._looks_like_encrypted_script(full))
                if is_media or is_script:
                    info['encrypted_files'] += 1
                    if is_media:
                        info['media_files'] += 1
                    else:
                        info['script_files'] += 1
                info['total_files'] += 1
        return info

    # ============ Unpack ============

    def unpack(
        self,
        target: str,
        options: UnpackOptions,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> UnpackResult:
        """Дешифрует папку GS-игры или отдельный зашифрованный файл."""
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

    def _unpack_dir(
        self,
        target: str,
        output_dir: str,
        options: UnpackOptions,
        result: UnpackResult,
        progress_callback: Optional[ProgressCallback],
    ) -> None:
        """Проходит по дереву папки игры и дешифрует зашифрованные ресурсы."""
        # Сначала собираем список, чтобы знать total для прогресса.
        tasks: List[Tuple[str, str, bool]] = []  # (full_path, rel_path, is_media)
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if d not in self._SKIP_DIRS]
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, target)
                ext = os.path.splitext(fn)[1].lower()
                # Пропускаем движок/окружение NW.js — это не ресурсы игры.
                if ext in self._SKIP_EXTS:
                    continue
                if fn.lower() in ('package.json', 'signature', 'steam_appid.txt'):
                    continue
                is_media = ext in self.MEDIA_EXTS and self._is_encrypted(full)
                # data/*.js — зашифрованные скрипты, кроме открытых data/lib/*.js
                in_data = (os.sep + 'data' + os.sep) in (root + os.sep)
                in_lib = (os.sep + 'data' + os.sep + 'lib' + os.sep) in (root + os.sep)
                is_script = (in_data and not in_lib and ext == '.js'
                             and self._looks_like_encrypted_script(full))
                if is_media or is_script:
                    tasks.append((full, rel, is_media))

        total = len(tasks)
        for i, (full, rel, is_media) in enumerate(tasks):
            try:
                with open(full, 'rb') as f:
                    data = f.read()
                out_data = self._xor(data)
                # Расширение оставляем как есть — после дешифровки это валидный
                # PNG/JPG/OGG/...; .json.js остаётся .json.js (это JS-скрипты).
                self._write_data(output_dir, rel, out_data, options, result)
            except OSError as e:
                result.errors.append(f'{rel}: {e}')
            if progress_callback:
                try:
                    progress_callback(rel, i + 1, total)
                except Exception:
                    pass

    def _unpack_file(
        self,
        target: str,
        output_dir: str,
        options: UnpackOptions,
        result: UnpackResult,
        progress_callback: Optional[ProgressCallback],
    ) -> None:
        """Дешифрует один зашифрованный GS-файл (по содержимому, без маркера)."""
        basename = os.path.basename(target)
        try:
            with open(target, 'rb') as f:
                data = f.read()
            out_data = self._xor(data)
            self._write_data(output_dir, basename, out_data, options, result)
        except OSError as e:
            result.errors.append(f'{basename}: {e}')
        if progress_callback:
            try:
                progress_callback(basename, 1, 1)
            except Exception:
                pass

    # ============ Helpers ============

    @classmethod
    def _xor(cls, data: bytes) -> bytes:
        """XOR-дешифровка циклическим GS-ключом."""
        k = cls.KEY
        klen = len(k)
        return bytes(data[i] ^ k[i % klen] for i in range(len(data)))

    @classmethod
    def _is_encrypted(cls, filepath: str) -> bool:
        """True, если после XOR появляется валидная медиа-сигнатура."""
        return FormatDetector.is_gs_nwjs_encrypted_file(filepath)

    @classmethod
    def _looks_like_encrypted_script(cls, filepath: str) -> bool:
        """Эвристика: data/*.js — зашифрованный скрипт.

        После XOR первые байты обычно начинают валидный JS: это литералы
        вроде ``GS.dataCache['...']``, ``(``, ``function``, ``var`` и т.п.
        Открытые движковые скрипты сюда не попадают (они в data/lib/).
        Мы проверяем, что декодированный текст начинается с ASCII-печатного
        JS-токена, а исходный (до XOR) — нет.
        """
        try:
            with open(filepath, 'rb') as f:
                head = f.read(32)
        except (OSError, PermissionError):
            return False
        if not head:
            return False
        dec = cls._xor(head)
        # Декодированный текст должен быть печатным ASCII (JS-источник).
        try:
            text = dec.decode('ascii')
        except UnicodeDecodeError:
            return False
        if not text or not text[0].isalnum() and text[0] not in "(_'\"":
            return False
        # Все байты декодированной головы — печатные или пробельные.
        return all(c == '\t' or c == '\n' or c == '\r' or 0x20 <= ord(c) < 0x7f
                   for c in text)

    def _write_data(
        self,
        output_dir: str,
        rel_path: str,
        data: bytes,
        options: UnpackOptions,
        result: UnpackResult,
    ) -> None:
        """Безопасно пишет data в output_dir с санитизацией пути."""
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
            raise PathTraversalError(f'Absolute path: {entry_path}')
        if ':' in entry_path[:3]:
            raise PathTraversalError(f'Absolute path: {entry_path}')

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
            raise PathTraversalError(f'Empty path: {entry_path}')

        safe_rel = '/'.join(safe_parts)
        safe_abs = os.path.abspath(os.path.join(output_dir, safe_rel))
        output_abs = os.path.abspath(output_dir)
        if not safe_abs.startswith(output_abs + os.sep) and safe_abs != output_abs:
            raise PathTraversalError(f'Path traversal attempt: {entry_path}')

        return safe_rel
