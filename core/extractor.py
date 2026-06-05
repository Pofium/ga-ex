import os
import sys
from typing import List, Callable, Optional

from core.rpa_reader import RpaReader, RpaEntry
from core.errors import (
    PathTraversalError, PermissionError, DiskSpaceError, PathLengthError
)


INVALID_FN_CHARS = '<>:"/\\|?*'
INVALID_FN_REPLACE = '_'
RESERVED_WIN_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
}


def enable_long_path_support() -> bool:
    """Включает поддержку длинных путей Windows (\\?\\ префикс)."""
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.ntdll.RtlSetLongPathSupport.argtypes = [ctypes.c_char]
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

    name = name.rstrip(' .')
    name = name.strip()

    if not name:
        return '_'

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
    """Преобразует путь в расширенный формат Windows (\\?\\)."""
    if sys.platform == 'win32' and not path.startswith('\\\\?\\'):
        if path.startswith('\\\\'):
            return '\\\\?\\UNC\\' + path[2:]
        return '\\\\?\\' + os.path.abspath(path)
    return path


class RpaExtractor:
    MAX_WINDOWS_PATH = 260
    MAX_WINDOWS_EXTENDED_PATH = 32767

    def __init__(
        self,
        rpa_path: str,
        output_dir: str,
        sanitize_names: bool = True,
        continue_on_error: bool = True,
        use_long_paths: bool = True,
    ):
        self.rpa_path = rpa_path
        self.output_dir = os.path.abspath(output_dir)
        self.sanitize_names = sanitize_names
        self.continue_on_error = continue_on_error
        self.use_long_paths = use_long_paths
        self._cancel_requested = False
        self.skipped_files: List[dict] = []

        if self.use_long_paths:
            enable_long_path_support()

    def cancel(self) -> None:
        self._cancel_requested = True

    def extract(
        self,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> List[str]:
        self._validate_output_dir()
        extracted_files: List[str] = []
        entries: List[RpaEntry] = []

        with RpaReader(self.rpa_path) as reader:
            entries = reader.get_entries()

        total = len(entries)
        for i, entry in enumerate(entries):
            if self._cancel_requested:
                break

            if progress_callback:
                progress_callback(entry.path, i + 1, total)

            try:
                safe_path = self._safe_join(entry.path)
                self._extract_entry(entry, safe_path)
                extracted_files.append(safe_path)
            except PathTraversalError as e:
                self.skipped_files.append({
                    'path': entry.path,
                    'reason': f'path_traversal: {e}',
                })
                if not self.continue_on_error:
                    raise
            except PermissionError:
                self.skipped_files.append({
                    'path': entry.path,
                    'reason': 'permission_denied',
                })
                if not self.continue_on_error:
                    raise
            except OSError as e:
                self.skipped_files.append({
                    'path': entry.path,
                    'reason': f'os_error: {e}',
                })
                if not self.continue_on_error:
                    raise

        return extracted_files

    def _validate_output_dir(self) -> None:
        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except PermissionError:
            raise PermissionError(f"No write permission in: {self.output_dir}")
        except OSError as e:
            raise PermissionError(f"Cannot create directory {self.output_dir}: {e}")

        if not os.access(self.output_dir, os.W_OK):
            raise PermissionError(f"No write permission in: {self.output_dir}")

    def _safe_join(self, entry_path: str) -> str:
        norm_path = os.path.normpath(entry_path).replace('\\', '/')
        norm_path = norm_path.lstrip('/')

        if norm_path.startswith('/') or norm_path.startswith('\\'):
            raise PathTraversalError(f"Absolute path in archive: {entry_path}")

        if '..' in norm_path.split('/') or norm_path.startswith('..'):
            raise PathTraversalError(f"Path traversal attempt detected: {entry_path}")

        parts = norm_path.split('/')
        safe_parts: List[str] = []
        for part in parts:
            if not part or part == '.':
                continue
            if part == '..':
                raise PathTraversalError(f"Path traversal attempt detected: {entry_path}")
            if ':' in part or '\\' in part:
                raise PathTraversalError(f"Invalid path component: {part}")
            if self.sanitize_names:
                part = sanitize_filename(part)
            safe_parts.append(part)

        if not safe_parts:
            raise PathTraversalError(f"Empty path in archive: {entry_path}")

        safe_rel = '/'.join(safe_parts)
        safe_abs = os.path.join(self.output_dir, safe_rel)
        abs_output = os.path.abspath(self.output_dir)
        abs_safe = os.path.abspath(safe_abs)

        if not abs_safe.startswith(abs_output + os.sep) and abs_safe != abs_output:
            raise PathTraversalError(f"Path traversal attempt: {entry_path}")

        return safe_rel

    def _extract_entry(self, entry: RpaEntry, safe_rel_path: str) -> None:
        entry_dir = os.path.join(self.output_dir, os.path.dirname(safe_rel_path))
        if entry_dir and not os.path.exists(entry_dir):
            try:
                os.makedirs(entry_dir, exist_ok=True)
            except PermissionError:
                raise PermissionError(f"No permission to create: {entry_dir}")
            except OSError as e:
                raise PermissionError(f"Cannot create directory {entry_dir}: {e}")

        entry_file = os.path.join(self.output_dir, safe_rel_path)

        path_too_long = (
            sys.platform == 'win32'
            and len(entry_file) >= self.MAX_WINDOWS_PATH
            and not entry_file.startswith('\\\\?\\')
        )

        if path_too_long and not self.use_long_paths:
            raise PathLengthError(
                f"Path too long ({len(entry_file)} chars): {entry_file}"
            )

        try:
            with RpaReader(self.rpa_path) as reader:
                data = reader.read_file_data(entry)

            write_path = entry_file
            if self.use_long_paths and sys.platform == 'win32':
                write_path = to_extended_path(entry_file)

            with open(write_path, 'wb') as f:
                f.write(data)

        except PermissionError:
            raise PermissionError(f"No permission to write: {entry_file}")
        except OSError as e:
            if "no space left" in str(e).lower():
                raise DiskSpaceError(f"Not enough disk space to write: {entry_file}")
            raise


def extract_rpa(
    rpa_path: str,
    output_dir: str,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
    sanitize_names: bool = True,
    continue_on_error: bool = True,
    use_long_paths: bool = True,
) -> List[str]:
    extractor = RpaExtractor(
        rpa_path,
        output_dir,
        sanitize_names=sanitize_names,
        continue_on_error=continue_on_error,
        use_long_paths=use_long_paths,
    )
    return extractor.extract(progress_callback)
