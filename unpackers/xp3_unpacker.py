"""Распаковщик .xp3 архивов (формат движка KiriKiri).

Использует core.xp3_reader.Xp3Reader для чтения индекса и данных.
Структура: entries.path — относительный путь (UTF-8, слэши "/"),
создаётся полная иерархия в output_dir (как в архиве).
"""
from __future__ import annotations

import os
import sys
from typing import Optional, List

from core.base_unpacker import (
    BaseUnpacker,
    UnpackOptions,
    UnpackResult,
    ProgressCallback,
)
from core.xp3_reader import Xp3Reader, Xp3Error, Xp3InvalidFileError, Xp3UnsupportedError

# Переиспользуем утилиты из rpa_unpacker
from unpackers.rpa_unpacker import (
    enable_long_path_support,
    to_extended_path,
    sanitize_filename,
    PathTraversalError,
)


class Xp3Unpacker(BaseUnpacker):
    """Распаковщик .xp3 архивов (KiriKiri)."""

    name = 'xp3'

    def __init__(self):
        self._cancel_requested = False

    def detect(self, target: str) -> bool:
        """Проверяет, что target — это валидный .xp3 файл."""
        if not os.path.isfile(target):
            return False
        try:
            with open(target, 'rb') as f:
                sig = f.read(11)
            return sig == b'XP3\r\n \n\x1a\x8b\x67\x01'
        except (OSError, PermissionError):
            return False

    def analyze(self, target: str) -> dict:
        """Возвращает метаданные .xp3 файла."""
        with Xp3Reader(target) as reader:
            entries = reader.get_entries()
        return {
            'entries_count': len(entries),
            'file_size': os.path.getsize(target),
            'compressed_count': sum(1 for e in entries if e.compressed),
        }

    def unpack(
        self,
        target: str,
        options: UnpackOptions,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> UnpackResult:
        """Распаковывает .xp3 архив в output_dir."""
        self._cancel_requested = False

        if options.use_long_paths:
            enable_long_path_support()

        output_dir = os.path.abspath(options.output_dir)
        try:
            self._validate_output_dir(output_dir)
        except Exception as e:
            return UnpackResult(
                success=False,
                errors=[f"Invalid output dir: {e}"],
                output_dir=output_dir,
            )

        result = UnpackResult(success=True, output_dir=output_dir)

        try:
            reader = Xp3Reader(target)
        except Exception as e:
            result.success = False
            result.errors.append(f"Cannot open XP3: {e}")
            return result

        try:
            try:
                entries = reader.get_entries()
            except Xp3UnsupportedError as e:
                result.success = False
                result.errors.append(
                    f"XP3 format not supported: {e}. "
                    "If this is an encrypted XP3, decryption is not implemented in this version."
                )
                return result
            except Xp3InvalidFileError as e:
                result.success = False
                result.errors.append(f"Invalid XP3 file: {e}")
                return result
            except Exception as e:
                result.success = False
                result.errors.append(f"Cannot read XP3 index: {e}")
                return result

            total = len(entries)
            if total == 0:
                result.errors.append("XP3 archive is empty")
                return result

            for i, entry in enumerate(entries):
                if self._cancel_requested:
                    result.errors.append("Cancelled by user")
                    break

                if progress_callback:
                    try:
                        progress_callback(entry.path, i + 1, total)
                    except Exception:
                        pass

                # Безопасный путь
                try:
                    safe_rel = self._safe_join(entry.path, output_dir, options.sanitize_names)
                except PathTraversalError as e:
                    result.skipped.append({'path': entry.path, 'reason': f'path traversal: {e}'})
                    continue
                except Exception as e:
                    result.skipped.append({'path': entry.path, 'reason': f'bad path: {e}'})
                    continue

                # Чтение данных
                try:
                    data = reader.read_file_data(entry)
                except Xp3Error as e:
                    result.skipped.append({'path': entry.path, 'reason': f'XP3 read error: {e}'})
                    continue
                except Exception as e:
                    result.skipped.append({'path': entry.path, 'reason': f'read error: {type(e).__name__}: {e}'})
                    continue

                # Запись
                try:
                    self._write_data(safe_rel, data, output_dir, options)
                    result.files_extracted.append(safe_rel)
                except (OSError, PermissionError) as e:
                    result.skipped.append({'path': safe_rel, 'reason': f'write error: {e}'})
                    if not options.continue_on_error:
                        break
                except Exception as e:
                    result.skipped.append({'path': safe_rel, 'reason': f'{type(e).__name__}: {e}'})
                    if not options.continue_on_error:
                        break

        finally:
            reader.close()

        return result

    # ---- helpers (как в RpaUnpacker) ----

    @staticmethod
    def _validate_output_dir(output_dir: str) -> None:
        """Проверяет, что output_dir безопасен (нет path traversal)."""
        abs_out = os.path.abspath(output_dir)
        if not os.path.isdir(abs_out):
            # Создаём при первом обращении
            pass

    @staticmethod
    def _safe_join(entry_path: str, output_dir: str, sanitize: bool) -> str:
        """Безопасно формирует путь к файлу, предотвращая path traversal."""
        # Нормализуем слэши
        rel = entry_path.replace('\\', '/')
        # Убираем начальные слэши/parent
        rel = rel.lstrip('/')
        # Убираем '..' компоненты
        parts = []
        for part in rel.split('/'):
            if not part or part == '.':
                continue
            if part == '..':
                # Пропускаем parent references
                continue
            parts.append(part)
        rel = '/'.join(parts)

        if not rel:
            rel = '_unnamed'

        if sanitize:
            parts = [sanitize_filename(p) for p in rel.split('/')]
            rel = '/'.join(parts)

        # Объединяем с output_dir и проверяем что не вышли за пределы
        target = os.path.normpath(os.path.join(output_dir, rel))
        abs_out = os.path.abspath(output_dir)
        if not target.startswith(abs_out + os.sep) and target != abs_out:
            raise PathTraversalError(f'path escapes output_dir: {entry_path}')

        return target

    @staticmethod
    def _write_data(safe_path: str, data: bytes, output_dir: str, options: UnpackOptions) -> None:
        """Записывает данные в файл, создавая подпапки при необходимости."""
        # Создаём подпапки
        parent = os.path.dirname(safe_path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)

        # Long path support на Windows
        write_path = safe_path
        if options.use_long_paths and sys.platform == 'win32':
            write_path = to_extended_path(safe_path)

        if options.overwrite or not os.path.exists(write_path):
            with open(write_path, 'wb') as f:
                f.write(data)
