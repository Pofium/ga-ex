"""Unpacker для Wolf RPG Editor .wolf архивов.

Wolf RPG Editor — японский движок для создания RPG.
Формат .wolf:
  - Wolf RPG Editor 1.x: ZIP-подобный архив с паролем (или без)
  - Wolf RPG Editor 2.x: проприетарный формат со сжатием LZ4

Мы пробуем:
  1. Открыть как ZIP (многие .wolf — это просто переименованные zip)
  2. Парсить как сырой заголовок WOLF-формата
"""
from __future__ import annotations

import os
import struct
import zipfile
from typing import List, Optional

from core.base_unpacker import (
    BaseUnpacker, UnpackOptions, UnpackResult, ProgressCallback,
)


class WolfUnpacker(BaseUnpacker):
    """Распаковщик Wolf RPG Editor .wolf архивов."""

    name = 'wolf'

    @classmethod
    def detect(cls, target: str) -> bool:
        if not os.path.isfile(target):
            return False
        if not target.lower().endswith('.wolf'):
            return False
        return True

    def analyze(self, target: str) -> dict:
        info = {
            'type': 'wolf_rpg',
            'detected': self.detect(target),
            'file_size': os.path.getsize(target) if os.path.isfile(target) else 0,
            'error': None,
        }
        if not info['detected']:
            return info
        try:
            # Пробуем как ZIP
            with zipfile.ZipFile(target, 'r') as zf:
                names = zf.namelist()
                info['format'] = 'zip'
                info['file_count'] = len(names)
                info['sample_files'] = names[:10]
                if len(names) > 10:
                    info['sample_files'].append(f'... (+{len(names) - 10} more)')
                return info
        except (zipfile.BadZipFile, zipfile.LargeZipFile):
            pass

        # Не ZIP — читаем магию
        try:
            with open(target, 'rb') as f:
                head = f.read(16)
            magic = head[:4]
            info['format'] = 'raw'
            info['magic'] = magic.hex()
            info['note'] = 'Not a ZIP archive; raw binary format'
        except Exception as e:
            info['error'] = f'{type(e).__name__}: {e}'
        return info

    def unpack(
        self,
        target: str,
        options: UnpackOptions,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> UnpackResult:
        result = UnpackResult(success=False, output_dir=options.output_dir)

        if not self.detect(target):
            result.errors.append(
                f'{os.path.basename(target)}: не Wolf RPG архив'
            )
            return result

        output_dir = options.output_dir
        os.makedirs(output_dir, exist_ok=True)

        # Пробуем 1: ZIP
        try:
            with zipfile.ZipFile(target, 'r') as zf:
                names = zf.namelist()
                if names:
                    total = len(names)
                    for idx, name in enumerate(names, 1):
                        try:
                            data = zf.read(name)
                        except RuntimeError as e:
                            # Зашифрованный ZIP
                            result.warnings.append(
                                f'{name}: encrypted (Wolf RPG 1.x password-protected)'
                            )
                            continue

                        # Безопасный путь
                        safe = name.replace('..', '_').replace('\\', '/')
                        out_path = os.path.join(output_dir, safe)
                        out_subdir = os.path.dirname(out_path)
                        if out_subdir:
                            os.makedirs(out_subdir, exist_ok=True)

                        if name.endswith('/') or data is None:
                            continue  # папка

                        with open(out_path, 'wb') as f:
                            f.write(data)
                        result.files_extracted.append(out_path)

                        if progress_callback:
                            try:
                                progress_callback(name, idx, total)
                            except Exception:
                                pass

                    result.success = True
                    return result
        except (zipfile.BadZipFile, zipfile.LargeZipFile):
            pass

        # Пробуем 2: raw binary WOLF header
        try:
            with open(target, 'rb') as f:
                magic = f.read(4)
            # Wolf RPG Editor 2.x формат может иметь "WOLF" магию
            if magic == b'WOLF':
                result.warnings.append(
                    'Wolf RPG Editor 2.x формат — извлечение only заголовка '
                    '(полная поддержка TBD)'
                )
                # Сохраняем as-is
                out_path = os.path.join(output_dir, f'{os.path.basename(target)}.bin')
                with open(target, 'rb') as src, open(out_path, 'wb') as dst:
                    dst.write(src.read())
                result.files_extracted.append(out_path)
                result.success = True
                return result
        except (OSError, PermissionError) as e:
            result.errors.append(f'{os.path.basename(target)}: {e}')
            return result

        # Ничего не сработало
        result.warnings.append(
            'Не удалось распаковать .wolf — не ZIP и не WOLF magic. '
            'Возможно, используется шифрование Wolf RPG Editor 1.x.'
        )
        # Сохраняем as-is
        out_path = os.path.join(output_dir, f'{os.path.basename(target)}.bin')
        try:
            with open(target, 'rb') as src, open(out_path, 'wb') as dst:
                dst.write(src.read())
            result.files_extracted.append(out_path)
        except OSError as e:
            result.errors.append(f'{os.path.basename(target)}: {e}')
            return result

        result.success = True
        return result
