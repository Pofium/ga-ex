"""Unpacker для Godot Engine .pck архивов.

Формат (по Godot source):
  - GDPC magic в начале ИЛИ в конце файла (зависит от версии)
  - Version (4 байта)
  - Engine config
  - File index

Полная реализация: pip install gdtoolkit (только .tscn, не .pck)
или pyrite, godot-pck-tools.
"""
from __future__ import annotations

import os
import sys
from typing import List, Optional

from core.base_unpacker import (
    BaseUnpacker, UnpackOptions, UnpackResult, ProgressCallback,
)
from unpackers.rpa_unpacker import (
    enable_long_path_support, sanitize_filename, PathTraversalError,
)

GODOT_PCK_MAGIC = b'GDPC'


class GodotPckUnpacker(BaseUnpacker):
    """Unpacker для Godot Engine .pck."""
    name = 'godot_pck'

    @classmethod
    def detect(cls, target: str) -> bool:
        if not os.path.isfile(target):
            return False
        if not target.lower().endswith('.pck'):
            return False
        try:
            # Godot PCK magic может быть в начале или в конце файла
            with open(target, 'rb') as f:
                head = f.read(4)
            if head == GODOT_PCK_MAGIC:
                return True
            # Или в конце (последние 4 байта до magic)
            f.seek(-4, 2)
            tail = f.read(4)
            return tail == GODOT_PCK_MAGIC
        except (OSError, PermissionError):
            return False

    def analyze(self, target: str) -> dict:
        return {
            'type': 'godot_pck',
            'detected': self.detect(target),
            'note': 'Godot PCK: установите godot-pck-tools для полной поддержки',
        }

    def unpack(
        self,
        target: str,
        options: UnpackOptions,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> UnpackResult:
        result = UnpackResult(success=False, output_dir=options.output_dir)
        result.errors.append(
            f'{os.path.basename(target)}: Godot .pck пока не поддерживается. '
            f'Используйте godot-pck-tools (https://github.com/eternity7744/godot-pck-tools) '
            f'или утилиту GDOffsetFinder.'
        )
        return result
