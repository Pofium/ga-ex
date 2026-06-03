import os
import shutil
from pathlib import Path
from typing import Callable, Optional, List
from core.rpa_reader import RpaReader, RpaEntry
from core.errors import PathTraversalError, PermissionError, DiskSpaceError, PathLengthError


class RpaExtractor:
    MAX_WINDOWS_PATH = 260
    MAX_WINDOWS_EXTENDED_PATH = 32767

    def __init__(self, rpa_path: str, output_dir: str):
        self.rpa_path = rpa_path
        self.output_dir = os.path.abspath(output_dir)
        self._cancel_requested = False

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

            safe_path = self._safe_join(entry.path)

            if progress_callback:
                progress_callback(entry.path, i + 1, total)

            self._extract_entry(entry, safe_path)
            extracted_files.append(safe_path)

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

        if '..' in norm_path or '..' in entry_path:
            raise PathTraversalError(f"Path traversal attempt detected: {entry_path}")

        parts = norm_path.split('/')
        for part in parts:
            if part in ('', '.', '..'):
                continue
            if '/' in part or '\\' in part or ':' in part:
                raise PathTraversalError(f"Invalid path component: {part}")

        safe_path = os.path.join(self.output_dir, norm_path)

        abs_output = os.path.abspath(self.output_dir)
        abs_safe = os.path.abspath(safe_path)

        if not abs_safe.startswith(abs_output + os.sep) and abs_safe != abs_output:
            raise PathTraversalError(f"Path traversal attempt: {entry_path}")

        return norm_path

    def _extract_entry(self, entry: RpaEntry, safe_path: str) -> None:
        entry_dir = os.path.join(self.output_dir, os.path.dirname(safe_path))
        if entry_dir and not os.path.exists(entry_dir):
            try:
                os.makedirs(entry_dir, exist_ok=True)
            except PermissionError:
                raise PermissionError(f"No permission to create: {entry_dir}")
            except OSError as e:
                raise PermissionError(f"Cannot create directory {entry_dir}: {e}")

        entry_file = os.path.join(self.output_dir, safe_path)

        if len(entry_file) > self.MAX_WINDOWS_PATH and not entry_file.startswith('\\\\?\\'):
            raise PathLengthError(
                f"Path too long ({len(entry_file)} chars): {entry_file}. "
                f"Consider using extended path prefix."
            )

        try:
            with RpaReader(self.rpa_path) as reader:
                data = reader.read_file_data(entry)

            with open(entry_file, 'wb') as f:
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
    progress_callback: Optional[Callable[[str, int, int], None]] = None
) -> List[str]:
    extractor = RpaExtractor(rpa_path, output_dir)
    return extractor.extract(progress_callback)
