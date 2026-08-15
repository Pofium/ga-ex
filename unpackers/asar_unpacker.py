from __future__ import annotations

import json
import os
import shutil
import struct
from typing import Iterable, List, Optional, Tuple

from core.base_unpacker import (
    BaseUnpacker, ProgressCallback, UnpackOptions, UnpackResult,
)
from unpackers.rpa_unpacker import (
    PathTraversalError, enable_long_path_support, sanitize_filename,
    to_extended_path,
)


def _read_uint32_le(data: bytes, offset: int) -> int:
    return struct.unpack_from('<I', data, offset)[0]


def _parse_asar_header(asar_path: str) -> Tuple[dict, int]:
    with open(asar_path, 'rb') as f:
        head = f.read(8)
        if len(head) < 8:
            raise ValueError('file too small for asar header')

        size_pickle_len = _read_uint32_le(head, 0)
        if size_pickle_len != 4:
            raise ValueError('invalid asar header (pickle length)')

        header_size = _read_uint32_le(head, 4)
        if header_size <= 0:
            raise ValueError('invalid asar header (header_size)')

        header_pickle = f.read(header_size)
        if len(header_pickle) != header_size:
            raise ValueError('unexpected EOF while reading header')

    if len(header_pickle) < 4:
        raise ValueError('invalid header pickle')

    # Внутренний pickle хранит JSON-заголовок. Есть два варианта структуры
    # в зависимости от сборщика asar:
    #   1) классический asar (npm):  [uint32 json_len][JSON][padding]
    #      JSON начинается на смещении 4, длина — json_len.
    #   2) TyranoBuilder/некоторые сборки Electron:  [uint32 json_len][uint32 json_len-4][JSON]
    #      дополнительный uint32 (capacity) перед JSON, JSON на смещении 8.
    # Проверяем оба варианта: для каждого старт-смещения читаем поле длины
    # перед ним и пробуем распарсить ровно json_len байт (без trailing-мусора).
    declared_len = _read_uint32_le(header_pickle, 0)
    header = None
    candidates: List[Tuple[int, int]] = []
    # Вариант 1: JSON на смещении 4, длина = declared_len
    if declared_len > 0 and 4 + declared_len <= len(header_pickle):
        candidates.append((4, declared_len))
    # Вариант 2: второй uint32 — это реальная длина JSON на смещении 8
    if len(header_pickle) >= 12:
        alt_len = _read_uint32_le(header_pickle, 4)
        if alt_len > 0 and 8 + alt_len <= len(header_pickle):
            candidates.append((8, alt_len))

    # Fallback: поиск '{' и парсинг до конца pickle (на случай нестандартной длины)
    brace = header_pickle.find(b'{')
    if brace >= 0:
        candidates.append((brace, len(header_pickle) - brace))

    for start, length in candidates:
        if start < 0 or length <= 0 or start + length > len(header_pickle):
            continue
        if header_pickle[start:start + 1] != b'{':
            continue
        json_bytes = header_pickle[start:start + length]
        try:
            parsed = json.loads(json_bytes.decode('utf-8'))
        except Exception:
            continue
        if isinstance(parsed, dict) and 'files' in parsed:
            header = parsed
            break

    if header is None:
        raise ValueError('cannot parse header JSON (no valid asar header found)')

    base_offset = 8 + header_size
    return header, base_offset


def _iter_entries(node: dict, prefix: str = '') -> Iterable[Tuple[str, dict]]:
    files = node.get('files', {})
    if not isinstance(files, dict):
        return
    for name, child in files.items():
        if not isinstance(child, dict):
            continue
        child_path = f'{prefix}{name}'
        if 'files' in child:
            yield from _iter_entries(child, prefix=f'{child_path}/')
        else:
            yield child_path, child


class ElectronAsarUnpacker(BaseUnpacker):
    name = 'electron_asar'

    @staticmethod
    def _safe_join(entry_path: str, output_dir: str, sanitize: bool) -> str:
        rel = entry_path.replace('\\', '/').lstrip('/')
        parts = []
        for part in rel.split('/'):
            part = part.strip()
            if not part or part == '.':
                continue
            if part == '..':
                continue
            parts.append(part)
        rel = '/'.join(parts) or '_unnamed'

        if sanitize:
            rel = '/'.join(sanitize_filename(p) for p in rel.split('/'))

        target = os.path.normpath(os.path.join(output_dir, rel))
        abs_out = os.path.abspath(output_dir)
        if not target.startswith(abs_out + os.sep) and target != abs_out:
            raise PathTraversalError(f'path escapes output_dir: {entry_path}')
        return target

    @classmethod
    def detect(cls, target: str) -> bool:
        if not os.path.isfile(target):
            return False
        if not target.lower().endswith('.asar'):
            return False
        try:
            header, _ = _parse_asar_header(target)
            return isinstance(header, dict) and isinstance(header.get('files'), dict)
        except Exception:
            return False

    def analyze(self, target: str) -> dict:
        info = {
            'type': 'electron_asar',
            'detected': self.detect(target),
            'file_size': os.path.getsize(target) if os.path.isfile(target) else 0,
            'file_count': 0,
            'error': None,
        }
        if not info['detected']:
            return info
        try:
            header, _ = _parse_asar_header(target)
            info['file_count'] = sum(1 for _p, _m in _iter_entries(header))
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
            result.errors.append(f'{os.path.basename(target)}: не похоже на Electron app.asar')
            return result

        if options.use_long_paths:
            enable_long_path_support()

        output_dir = os.path.abspath(options.output_dir)
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            result.errors.append(f'Не удалось создать {output_dir}: {e}')
            return result

        try:
            header, base_offset = _parse_asar_header(target)
        except Exception as e:
            result.errors.append(f'{os.path.basename(target)}: {type(e).__name__}: {e}')
            return result

        entries: List[Tuple[str, dict]] = list(_iter_entries(header))
        total = len(entries)
        if total == 0:
            result.warnings.append(f'{os.path.basename(target)}: 0 файлов в заголовке')
            result.success = True
            return result

        unpacked_root = f'{target}.unpacked'

        try:
            with open(target, 'rb') as f:
                for idx, (path_in_asar, meta) in enumerate(entries, 1):
                    if progress_callback:
                        try:
                            progress_callback(path_in_asar, idx, total)
                        except Exception:
                            pass

                    try:
                        out_path = self._safe_join(
                            entry_path=path_in_asar,
                            output_dir=output_dir,
                            sanitize=options.sanitize_names,
                        )
                    except PathTraversalError:
                        result.skipped.append({'path': path_in_asar, 'reason': 'unsafe path (path traversal blocked)'})
                        continue

                    out_dir = os.path.dirname(out_path)
                    if out_dir:
                        os.makedirs(out_dir, exist_ok=True)

                    if meta.get('link'):
                        result.skipped.append({'path': path_in_asar, 'reason': 'symlink is not supported'})
                        continue

                    if meta.get('unpacked'):
                        src = os.path.join(unpacked_root, path_in_asar.replace('/', os.sep))
                        if not os.path.isfile(src):
                            result.warnings.append(f'{path_in_asar}: unpacked file missing: {src}')
                            continue
                        try:
                            shutil.copyfile(to_extended_path(src), to_extended_path(out_path))
                        except OSError as e:
                            result.errors.append(f'{path_in_asar}: ошибка копирования: {e}')
                            if not options.continue_on_error:
                                return result
                            continue
                        result.files_extracted.append(out_path)
                        continue

                    if 'offset' not in meta or 'size' not in meta:
                        result.warnings.append(f'{path_in_asar}: нет offset/size в заголовке')
                        continue

                    try:
                        rel_off = int(str(meta.get('offset', '0')))
                        size = int(meta.get('size', 0))
                    except Exception:
                        result.warnings.append(f'{path_in_asar}: некорректный offset/size')
                        continue

                    if size < 0:
                        result.warnings.append(f'{path_in_asar}: некорректный размер ({size})')
                        continue
                    if size == 0:
                        with open(to_extended_path(out_path), 'wb') as wf:
                            wf.write(b'')
                        result.files_extracted.append(out_path)
                        continue

                    abs_off = base_offset + rel_off
                    f.seek(abs_off)
                    data = f.read(size)
                    if len(data) != size:
                        result.errors.append(f'{path_in_asar}: неожиданный EOF при чтении данных')
                        if not options.continue_on_error:
                            return result
                        continue

                    try:
                        with open(to_extended_path(out_path), 'wb') as wf:
                            wf.write(data)
                    except OSError as e:
                        result.errors.append(f'{path_in_asar}: ошибка записи: {e}')
                        if not options.continue_on_error:
                            return result
                        continue

                    result.files_extracted.append(out_path)
        except OSError as e:
            result.errors.append(f'{os.path.basename(target)}: {e}')
            return result

        result.success = len(result.errors) == 0
        return result
