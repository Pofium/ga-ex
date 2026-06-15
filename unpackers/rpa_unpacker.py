"""Реализация распаковщика RPA через BaseUnpacker."""
import os
import sys
from typing import Optional

from core.base_unpacker import BaseUnpacker, UnpackOptions, UnpackResult, ProgressCallback
from core.rpa_reader import RpaReader


# Недопустимые символы в именах файлов Windows.
INVALID_FN_CHARS = '<>:"/\\|?*'
INVALID_FN_REPLACE = '_'

# Зарезервированные имена Windows.
RESERVED_WIN_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
}


def enable_long_path_support() -> bool:
    """Включает поддержку длинных путей Windows."""
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.ntdll.RtlSetLongPathSupport(1)
            return True
        except Exception:
            pass
    return False


def sanitize_filename(name: str) -> str:
    """Заменяет недопустимые символы и нормализует имя файла."""
    if not name:
        return '_'

    for ch in INVALID_FN_CHARS:
        name = name.replace(ch, INVALID_FN_REPLACE)

    name = name.rstrip(' .').strip()
    if not name:
        return '_'

    # Защита зарезервированных имён (без расширения)
    if name.upper() in RESERVED_WIN_NAMES:
        name = f"_{name}"

    if '.' in name:
        stem, dot, ext = name.partition('.')
        if stem.upper() in RESERVED_WIN_NAMES:
            name = f"_{stem}{dot}{ext}"

    if len(name) > 240:
        if '.' in name:
            stem, dot, ext = name.rpartition('.')
            max_stem = 240 - len(dot) - len(ext)
            name = stem[:max_stem] + dot + ext
        else:
            name = name[:240]

    return name


def to_extended_path(path: str) -> str:
    """Преобразует путь в расширенный формат Windows (\\\\?\\)."""
    if sys.platform == 'win32' and not path.startswith('\\\\?\\'):
        if path.startswith('\\\\'):
            return '\\\\?\\UNC\\' + path[2:]
        return '\\\\?\\' + os.path.abspath(path)
    return path


class PathTraversalError(Exception):
    pass


class RpaUnpacker(BaseUnpacker):
    """Распаковщик RPA-архивов Ren'Py (v2.0/3.0/3.2)."""

    name = 'rpa'

    def __init__(self):
        self._cancel_requested = False

    def detect(self, target: str) -> bool:
        """Проверяет, что target — это валидный .rpa файл."""
        if not os.path.isfile(target):
            return False
        try:
            with open(target, 'rb') as f:
                signature = f.read(7)
            return signature.startswith(b'RPA-')
        except (OSError, PermissionError):
            return False

    def analyze(self, target: str) -> dict:
        """Возвращает метаданные RPA-файла (количество entries, размер)."""
        with RpaReader(target) as reader:
            entries = reader.get_entries()
        return {
            'version': reader.version,
            'entries_count': len(entries),
            'file_size': os.path.getsize(target),
        }

    def unpack(
        self,
        target: str,
        options: UnpackOptions,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> UnpackResult:
        """Распаковывает RPA-архив в указанную папку."""
        self._cancel_requested = False

        if options.use_long_paths:
            enable_long_path_support()

        output_dir = os.path.abspath(options.output_dir)
        self._validate_output_dir(output_dir)

        result = UnpackResult(success=True, output_dir=output_dir)

        try:
            with RpaReader(target) as reader:
                entries = reader.get_entries()
                file_size = os.path.getsize(target)
        except Exception as e:
            result.success = False
            result.errors.append(f"Cannot read archive: {e}")
            return result

        # Кешируем файловый дескриптор для эффективного чтения.
        with RpaReader(target) as reader:
            total = len(entries)
            for i, entry in enumerate(entries):
                if self._cancel_requested:
                    result.errors.append("Cancelled by user")
                    break

                if progress_callback:
                    progress_callback(entry.path, i + 1, total)

                try:
                    safe_rel = self._safe_join(entry.path, output_dir, options.sanitize_names)
                    data = reader.read_file_data(entry)
                    self._write_data(safe_rel, data, output_dir, options)
                    result.files_extracted.append(safe_rel)
                except PathTraversalError as e:
                    result.skipped.append({'path': entry.path, 'reason': f'path_traversal: {e}'})
                    if not options.continue_on_error:
                        result.success = False
                        result.errors.append(f"Path traversal: {entry.path}")
                        return result
                except PermissionError as e:
                    result.skipped.append({'path': entry.path, 'reason': f'permission: {e}'})
                    if not options.continue_on_error:
                        result.success = False
                        result.errors.append(f"Permission: {entry.path}")
                        return result
                except OSError as e:
                    result.skipped.append({'path': entry.path, 'reason': f'os_error: {e}'})
                    if not options.continue_on_error:
                        result.success = False
                        result.errors.append(f"OS error: {entry.path}")
                        return result

        return result

    def cancel(self) -> None:
        self._cancel_requested = True

    def _validate_output_dir(self, output_dir: str) -> None:
        try:
            os.makedirs(output_dir, exist_ok=True)
        except PermissionError as e:
            raise PermissionError(f"No write permission in: {output_dir}: {e}")
        except OSError as e:
            raise PermissionError(f"Cannot create directory {output_dir}: {e}")

        if not os.access(output_dir, os.W_OK):
            raise PermissionError(f"No write permission in: {output_dir}")

    def _safe_join(self, entry_path: str, output_dir: str, sanitize: bool) -> str:
        # Отклоняем абсолютные пути ДО любой нормализации
        if os.path.isabs(entry_path) or entry_path.startswith('/') or entry_path.startswith('\\'):
            raise PathTraversalError(f"Absolute path in archive: {entry_path}")
        if ':' in entry_path[:3]:  # Windows drive letter
            raise PathTraversalError(f"Absolute path in archive: {entry_path}")

        norm_path = entry_path.replace('\\', '/')

        # Path traversal: '..' как отдельный компонент
        if '..' in norm_path.split('/'):
            raise PathTraversalError(f"Path traversal attempt: {entry_path}")

        parts = norm_path.split('/')
        safe_parts = []
        for part in parts:
            if not part or part == '.':
                continue
            if part == '..':
                raise PathTraversalError(f"Path traversal attempt: {entry_path}")
            if ':' in part or '\\' in part:
                raise PathTraversalError(f"Invalid path component: {part}")
            if sanitize:
                part = sanitize_filename(part)
            safe_parts.append(part)

        if not safe_parts:
            raise PathTraversalError(f"Empty path in archive: {entry_path}")

        safe_rel = '/'.join(safe_parts)
        safe_abs = os.path.join(output_dir, safe_rel)
        abs_output = os.path.abspath(output_dir)
        abs_safe = os.path.abspath(safe_abs)

        if not abs_safe.startswith(abs_output + os.sep) and abs_safe != abs_output:
            raise PathTraversalError(f"Path traversal attempt: {entry_path}")

        return safe_rel

    def _write_data(
        self,
        safe_rel: str,
        data: bytes,
        output_dir: str,
        options: UnpackOptions,
    ) -> None:
        entry_dir = os.path.join(output_dir, os.path.dirname(safe_rel))
        if entry_dir and not os.path.exists(entry_dir):
            try:
                os.makedirs(entry_dir, exist_ok=True)
            except PermissionError as e:
                raise PermissionError(f"No permission to create: {entry_dir}: {e}")
            except OSError as e:
                raise PermissionError(f"Cannot create directory {entry_dir}: {e}")

        entry_file = os.path.join(output_dir, safe_rel)

        # Long path support
        if options.use_long_paths and sys.platform == 'win32':
            write_path = to_extended_path(entry_file)
        else:
            write_path = entry_file

        if not options.overwrite and os.path.exists(entry_file):
            return  # Skip existing files

        try:
            with open(write_path, 'wb') as f:
                f.write(data)
        except PermissionError as e:
            raise PermissionError(f"No permission to write: {entry_file}: {e}")
        except OSError as e:
            raise OSError(f"Write error: {entry_file}: {e}")
