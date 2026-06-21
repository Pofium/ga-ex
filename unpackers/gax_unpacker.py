"""CatSystem2 .gax распаковщик.

.gax — проприетарный зашифрованный формат изображений,
используемый в играх на движке CatSystem2 (戯画).
Magic: 00 00 00 01 (4 байта), затем зашифрованные данные.

Алгоритм шифрования использует per-game XOR-ключ, который
жёстко зашит в исполняемом файле игры. Этот unpacker:
1. Пробует 8 стандартных XOR-схем
2. Если передан exe игры — извлекает ключ и пробует его
3. Если ничего не подошло — сохраняет данные как .bin с диагностикой

Для автоматического извлечения ключа из exe см.
`core/gax_key_extractor.py`.
"""
from __future__ import annotations

import os
import struct
from typing import List, Optional, Tuple

from core.base_unpacker import (
    BaseUnpacker, UnpackOptions, UnpackResult, ProgressCallback,
)
from unpackers.rpa_unpacker import (
    enable_long_path_support, sanitize_filename, PathTraversalError,
)


# Известные сигнатуры изображений
IMAGE_SIGNATURES: List[Tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"BM", ".bmp"),
    (b"RIFF", ".webp"),
]


def _detect_image_signature(data: bytes) -> Optional[str]:
    """Определяет тип изображения по первым байтам."""
    if len(data) < 3:
        return None
    for sig, ext in IMAGE_SIGNATURES:
        if len(sig) <= len(data) and data.startswith(sig):
            return ext
    return None


def _try_decrypt(data: bytes, algorithm: str) -> bytes:
    """Пробует расшифровать .gax указанным алгоритмом."""
    size = len(data)
    out = bytearray(data)
    if algorithm == 'xor_size_le':
        key = size & 0xFFFFFFFF
        for i in range(4, size):
            out[i] ^= (key >> ((i & 3) * 8)) & 0xFF
            key = (key * 7 + 3) & 0xFFFFFFFF
    elif algorithm == 'xor_size_rotating':
        key = size & 0xFF
        for i in range(4, size):
            out[i] ^= key
            key = (key + 1) & 0xFF
    elif algorithm == 'xor_pos_byte':
        for i in range(4, size):
            out[i] ^= ((i + 4) & 0xFF)
    elif algorithm == 'xor_pos_byte_rev':
        for i in range(4, size):
            out[i] ^= ((255 - (i & 0xFF)) & 0xFF)
    elif algorithm == 'xor_magic_rot':
        key = 0x01000000
        for i in range(4, size):
            out[i] ^= (key >> ((i & 3) * 8)) & 0xFF
            key = (key * 7 + 3) & 0xFFFFFFFF
    elif algorithm == 'xor_size_xor_magic':
        key = size ^ 0x01000000
        for i in range(4, size):
            out[i] ^= (key >> ((i & 3) * 8)) & 0xFF
            key = (key * 7 + 3) & 0xFFFFFFFF
    elif algorithm == 'xor_0xff':
        for i in range(4, size):
            out[i] ^= 0xFF
    elif algorithm == 'not_bytes':
        for i in range(4, size):
            out[i] = (~out[i]) & 0xFF
    else:
        return data
    return bytes(out)


def _decrypt_with_key(data: bytes, base_key: int) -> bytes:
    """Расшифровывает .gax используя 32-битный ключ из exe."""
    size = len(data)
    out = bytearray(data)
    key = base_key & 0xFFFFFFFF
    for i in range(4, size):
        out[i] ^= (key >> ((i & 3) * 8)) & 0xFF
        key = (key * 7 + 3) & 0xFFFFFFFF
    return bytes(out)


def decrypt_gax(
    data: bytes,
    custom_key: Optional[int] = None,
) -> Tuple[Optional[bytes], Optional[str], str]:
    """Пытается расшифровать .gax данные.

    Args:
        data: Полные данные файла (включая magic).
        custom_key: Опциональный 32-битный ключ (например, из exe).

    Returns:
        Кортеж (decrypted_data, image_extension, algorithm_name).
        Если не удалось — decrypted_data is None.
    """
    # Сначала пробуем пользовательский ключ (если есть)
    if custom_key is not None:
        decrypted = _decrypt_with_key(data, custom_key)
        ext = _detect_image_signature(decrypted[4:16])
        if ext is not None:
            return decrypted, ext, f'custom_key_0x{custom_key:08x}'

    # Стандартные алгоритмы
    algorithms = [
        'xor_size_le',
        'xor_size_rotating',
        'xor_pos_byte',
        'xor_pos_byte_rev',
        'xor_magic_rot',
        'xor_size_xor_magic',
        'xor_0xff',
        'not_bytes',
    ]

    for algo in algorithms:
        decrypted = _try_decrypt(data, algo)
        ext = _detect_image_signature(decrypted[4:16])
        if ext is not None:
            return decrypted, ext, algo

    return None, None, ''


class GaxUnpacker(BaseUnpacker):
    """Распаковщик CatSystem2 .gax изображений."""

    name = 'gax'

    GAX_MAGIC = b'\x00\x00\x00\x01'

    @classmethod
    def detect(cls, target: str) -> bool:
        if not os.path.isfile(target):
            return False
        if not target.lower().endswith('.gax'):
            return False
        try:
            with open(target, 'rb') as f:
                head = f.read(4)
            return head == cls.GAX_MAGIC
        except (OSError, PermissionError):
            return False

    def analyze(self, target: str) -> dict:
        info = {
            'type': 'catsystem2_gax',
            'detected': self.detect(target),
            'note': (
                'CatSystem2 .gax: для расшифровки может потребоваться '
                'exe игры (см. опцию "EXE для .gax")'
            ),
            'size': os.path.getsize(target) if os.path.isfile(target) else 0,
        }
        return info

    def unpack(
        self,
        target: str,
        options: UnpackOptions,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> UnpackResult:
        enable_long_path_support()
        result = UnpackResult(success=True, output_dir=options.output_dir)

        try:
            base_name = sanitize_filename(
                os.path.splitext(os.path.basename(target))[0]
            )
            if not base_name:
                base_name = 'gax_output'

            with open(target, 'rb') as f:
                data = f.read()

            if not data.startswith(self.GAX_MAGIC):
                result.success = False
                result.errors.append(
                    f'{os.path.basename(target)}: неверный magic (ожидается 00 00 00 01)'
                )
                return result

            # Пытаемся извлечь ключ из exe (если указан)
            custom_key = None
            exe_used = None
            if options.game_exe_path and os.path.isfile(options.game_exe_path):
                try:
                    from core.gax_key_extractor import find_gax_key_in_exe
                    custom_key = find_gax_key_in_exe(options.game_exe_path)
                    if custom_key is not None:
                        exe_used = options.game_exe_path
                except Exception:
                    pass

            # Пытаемся расшифровать
            decrypted, ext, algo = decrypt_gax(data, custom_key)

            if decrypted is not None and ext is not None:
                # Успех — сохраняем
                safe_name = sanitize_filename(f'{base_name}{ext}')
                out_path = self._safe_join(options.output_dir, safe_name)
                with open(out_path, 'wb') as f:
                    f.write(decrypted)
                result.files_extracted.append({
                    'path': out_path,
                    'size': len(decrypted),
                    'algorithm': algo,
                    'format': ext.lstrip('.'),
                })
                if exe_used and 'custom_key' in algo:
                    result.warnings.append(
                        f'{os.path.basename(target)}: расшифровано ключом из exe '
                        f'({os.path.basename(exe_used)})'
                    )
            else:
                # Не удалось расшифровать — сохраняем как .bin
                safe_name = sanitize_filename(f'{base_name}.bin')
                out_path = self._safe_join(options.output_dir, safe_name)
                with open(out_path, 'wb') as f:
                    f.write(data)
                result.files_extracted.append({
                    'path': out_path,
                    'size': len(data),
                    'algorithm': 'raw',
                    'format': 'unknown',
                })
                if options.game_exe_path:
                    # exe был указан, но ключ не сработал
                    msg = (
                        f'{os.path.basename(target)}: '
                        f'не удалось расшифровать (CatSystem2 использует '
                        f'per-game XOR-ключ, который не удалось извлечь '
                        f'из exe). Файл сохранён как .bin. '
                        f'Используйте crass / arc_conv / Galatea для '
                        f'полной расшифровки этой игры.'
                    )
                else:
                    msg = (
                        f'{os.path.basename(target)}: '
                        f'не удалось расшифровать (попробованы 8 стандартных '
                        f'алгоритмов). Укажите путь к exe игры CatSystem2 '
                        f'в поле "EXE (для .gax)" — будет выполнена попытка '
                        f'извлечения ключа. Файл сохранён как .bin.'
                    )
                result.warnings.append(msg)

            if progress_callback:
                progress_callback(1, 1)

        except (OSError, PermissionError) as e:
            result.success = False
            result.errors.append(f'{os.path.basename(target)}: I/O ошибка: {e}')
        except PathTraversalError as e:
            result.success = False
            result.errors.append(f'{os.path.basename(target)}: небезопасный путь: {e}')
        except Exception as e:
            result.success = False
            result.errors.append(
                f'{os.path.basename(target)}: неожиданная ошибка: {e}'
            )

        return result

    def _safe_join(self, base: str, name: str) -> str:
        """Безопасное соединение путей с защитой от path traversal."""
        from unpackers.rpa_unpacker import sanitize_filename
        safe_name = sanitize_filename(name)
        out_path = os.path.join(base, safe_name)
        out_path = os.path.abspath(out_path)
        base_abs = os.path.abspath(base)
        if not out_path.startswith(base_abs):
            raise PathTraversalError(f'Path traversal detected: {out_path}')
        return out_path
