"""Generic 7-Zip fallback unpacker.

Использует 7-Zip CLI или py7zr для распаковки произвольных архивов, которые
не были распознаны специализированными unpacker'ами.

Поддерживает: 7z, RAR, ZIP, TAR, GZ, BZ2, XZ, LZMA, ZPAQ, ISO, MSI, CAB, NSIS,
Inno Setup (частично), и т.д.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import List, Optional, Tuple

from core.base_unpacker import (
    BaseUnpacker, UnpackOptions, UnpackResult, ProgressCallback,
)
from unpackers.rpa_unpacker import (
    enable_long_path_support, sanitize_filename, PathTraversalError,
)


SEVENZIP_EXTENSIONS = {
    '.7z', '.zip', '.rar', '.tar', '.gz', '.tgz', '.bz2', '.tbz2',
    '.xz', '.txz', '.lzma', '.cab', '.iso', '.msi', '.arj', '.ace',
    '.arc', '.lzh', '.lha', '.rpm', '.deb', '.cpio', '.zst', '.zstd',
}


class SevenZipUnpacker(BaseUnpacker):
    """Unpacker на базе 7-Zip CLI (fallback для неизвестных форматов)."""
    name = '7zip'

    def __init__(self) -> None:
        super().__init__()
        self._7z_path: Optional[str] = None

    def _find_7z(self) -> Optional[str]:
        """Ищет 7z в PATH и стандартных путях Windows."""
        if self._7z_path:
            return self._7z_path
        # Проверяем PATH
        path = shutil.which('7z') or shutil.which('7z.exe')
        if path:
            self._7z_path = path
            return path
        # Стандартные пути Windows
        candidates = [
            r'C:\Program Files\7-Zip\7z.exe',
            r'C:\Program Files (x86)\7-Zip\7z.exe',
            r'C:\tools\7-Zip\7z.exe',
        ]
        for c in candidates:
            if os.path.exists(c):
                self._7z_path = c
                return c
        return None

    @classmethod
    def detect(cls, target: str) -> bool:
        if not os.path.isfile(target):
            return False
        ext = os.path.splitext(target)[1].lower()
        return ext in SEVENZIP_EXTENSIONS

    def analyze(self, target: str) -> dict:
        return {
            'type': '7zip_fallback',
            'detected': self.detect(target),
            '7z_available': self._find_7z() is not None,
        }

    def unpack(
        self,
        target: str,
        options: UnpackOptions,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> UnpackResult:
        result = UnpackResult(success=False, output_dir=options.output_dir)
        sevenz = self._find_7z()
        if not sevenz:
            result.errors.append(
                '7-Zip CLI не найден. Установите 7-Zip с https://7-zip.org/ '
                'и добавьте в PATH.'
            )
            return result
        if not os.path.isfile(target):
            result.errors.append(f'Not found: {target}')
            return result

        output_dir = os.path.abspath(options.output_dir)
        os.makedirs(output_dir, exist_ok=True)

        try:
            # 7z x <archive> -o<output_dir> -y
            cmd = [sevenz, 'x', target, f'-o{output_dir}', '-y', '-bb1']
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=3600,
            )
            if proc.returncode == 0:
                result.success = True
                # 7z не выдаёт список файлов через CLI, поэтому проверяем результат
                for root, _dirs, files in os.walk(output_dir):
                    for f in files:
                        full = os.path.join(root, f)
                        rel = os.path.relpath(full, output_dir).replace('\\', '/')
                        result.files_extracted.append(rel)
            else:
                result.errors.append(
                    f'7z вернул код {proc.returncode}: {proc.stderr[:500]}'
                )
        except subprocess.TimeoutExpired:
            result.errors.append('7z: timeout (1 hour)')
        except (OSError, subprocess.SubprocessError) as e:
            result.errors.append(f'7z: {e}')

        return result
