"""Unpacker для Wolf RPG Editor .wolf архивов.

Формат (по Wolf RPG Editor docs):
  Header: 16+ байт — magic + индексы файлов
  Body: stream of records с переменным размером

Простой парсинг: найти все строки UTF-8 между \x00 и записать offsets.
Полная спецификация: https://www.wolf-rpg.com/
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


class WolfUnpacker(BaseUnpacker):
    """Unpacker для Wolf RPG Editor .wolf (best-effort).

    Wolf RPG использует собственный формат с версиями.
    Заголовок обычно содержит несколько int32 с информацией о файлах.
    """
    name = 'wolf'

    @classmethod
    def detect(cls, target: str) -> bool:
        if not os.path.isfile(target):
            return False
        if not target.lower().endswith('.wolf'):
            return False
        try:
            # Минимальная проверка: файл с расширением .wolf и размер > 100 bytes
            return os.path.getsize(target) > 100
        except OSError:
            return False

    def analyze(self, target: str) -> dict:
        return {
            'type': 'wolf',
            'detected': self.detect(target),
            'note': 'Wolf RPG: полная поддержка в будущих версиях',
        }

    def unpack(
        self,
        target: str,
        options: UnpackOptions,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> UnpackResult:
        result = UnpackResult(success=False, output_dir=options.output_dir)
        result.errors.append(
            f'{os.path.basename(target)}: Wolf RPG .wolf не поддерживается. '
            f'Используйте WOLF RPG Editor для официальной распаковки или подождите '
            f'полной реализации.'
        )
        return result
