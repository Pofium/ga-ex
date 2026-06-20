"""Unpacker для Unreal Engine .pak архивов.

Формат (по https://github.com/EpicGames/UnrealEngine и repak):
  Header: 0x5041 4b00 = 'PAK\0' (4 байта magic)
  Version: 4 байта little-endian
  Records: index + files

Полная реализация: pip install repak (Rust-based) или
unrealunzen (python, но неполный).
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

UNREAL_PAK_MAGIC = b'PAK\x00'


class UnrealPakUnpacker(BaseUnpacker):
    """Unpacker для Unreal Engine .pak (заглушка)."""
    name = 'pak'

    @classmethod
    def detect(cls, target: str) -> bool:
        if not os.path.isfile(target):
            return False
        if not target.lower().endswith('.pak'):
            return False
        try:
            with open(target, 'rb') as f:
                head = f.read(4)
            return head == UNREAL_PAK_MAGIC
        except (OSError, PermissionError):
            return False

    def analyze(self, target: str) -> dict:
        return {
            'type': 'unreal_pak',
            'detected': self.detect(target),
            'note': 'Unreal PAK: установите repak (Rust) для полной поддержки',
        }

    def unpack(
        self,
        target: str,
        options: UnpackOptions,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> UnpackResult:
        result = UnpackResult(success=False, output_dir=options.output_dir)
        result.errors.append(
            f'{os.path.basename(target)}: Unreal .pak пока не поддерживается. '
            f'Можно использовать repak (https://github.com/trumank/repak) или '
            f'UnrealPak.exe официально.'
        )
        return result
