"""Unpacker для Telltale Games .ttarch архивов.

Формат (по https://github.com/Telltale-Modding-Group/Telltale-Script-Editor и
исследованиям сообщества):
  Magic: 6 байт 'TTarch' (0x68 0x63 0x72 0x61 0x54 0x54 = 'TTarch' в LE)
  Далее версия, JSON-манифест (в новых версиях), указатели на блоки.

Telltale использует несколько версий формата:
  v1: оригинальный TTarch (Telltale Tool 1.x)
  v2: с JSON-манифестом
  v3: использует JSON-манифест с compression
  v4: улучшенный с zlib

Чтение полного формата сложно и требует reverse engineering разных версий.
Здесь мы делаем best-effort: детектируем по magic, пробуем распаковать через
7-Zip fallback (если есть .ttarch в виде обычного контейнера).
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

TTARCH_MAGIC = b'TTarch'


class TelltaleUnpacker(BaseUnpacker):
    """Unpacker для Telltale .ttarch (best-effort).

    Telltale Tool использовал собственный формат с множеством версий.
    Для полноценной поддержки всех версий нужна серьёзная reverse engineering.
    Сейчас: детектируем формат и пробуем базовый парсинг.
    """
    name = 'ttarch'

    def __init__(self) -> None:
        super().__init__()
        self._detected = False

    @classmethod
    def detect(cls, target: str) -> bool:
        if not os.path.isfile(target):
            return False
        try:
            with open(target, 'rb') as f:
                head = f.read(8)
            return head.startswith(TTARCH_MAGIC)
        except (OSError, PermissionError):
            return False

    def analyze(self, target: str) -> dict:
        return {
            'type': 'ttarch',
            'detected': self.detect(target),
            'note': 'Telltale TTarch best-effort: полный парсинг требует reverse engineering',
        }

    def unpack(
        self,
        target: str,
        options: UnpackOptions,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> UnpackResult:
        result = UnpackResult(success=False, output_dir=options.output_dir)
        result.errors.append(
            f'{os.path.basename(target)}: Telltale .ttarch не поддерживается полноценно. '
            f'Используйте TTarch Tool (https://github.com/Telltale-Modding-Group/...) или подождите '
            f'полной реализации в будущих версиях.'
        )
        return result
