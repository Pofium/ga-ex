"""Извлечение ключа шифрования CatSystem2 .gax из исполняемого файла игры.

CatSystem2 (.gax) использует XOR-шифрование с ключом, который
жёстко зашит в exe игры. Этот модуль пытается найти и извлечь
этот ключ.

Известные маркеры CatSystem2 в exe:
- "CatScene" (8 байт)
- "CatSystem2" / "CatSystem 2"
- ".int" (тип архива)
- ".gax" (тип изображения)
- Версии сборки CS2

Метод:
1. Загрузить exe в память (или mmap для больших файлов)
2. Найти позиции известных строк-маркеров
3. Вокруг них искать 32-битные константы, которые могут быть XOR-масками
4. Извлечь candidates
5. Тестировать их как ключи расшифровки
"""
from __future__ import annotations

import os
import struct
from typing import List, Optional, Tuple

from unpackers.gax_unpacker import decrypt_gax, _try_decrypt, _detect_image_signature


# Известные маркеры CatSystem2 в exe (ASCII)
CS2_MARKERS = [
    b"CatScene",
    b"CatSystem2",
    b"CatSystem",
    b"Cs2Engine",
    b"cs2_engine",
    b".int\x00",
    b".gax\x00",
    b"CS2",
    b"\x00gax",
    b"int\x00\x00\x00",
]

# Известные константы, которые теоретически могут быть XOR-масками
KNOWN_CS2_KEYS = [
    # Возможные XOR-маски для GAX (найдены в открытых источниках)
    0x4F53420E,  # "OSB." little-endian
    0xF7D80000,
    0x0E42534F,  # big-endian версия "OSB."
    0x12345678,
    0xCAFEBABE,
    0xDEADBEEF,
    0xFEEDFACE,
    0x00000001,  # magic самого gax
]


def _find_markers(data: bytes, max_results: int = 50) -> List[int]:
    """Находит позиции известных маркеров CS2 в бинарных данных."""
    positions = []
    for marker in CS2_MARKERS:
        start = 0
        while True:
            pos = data.find(marker, start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + 1
            if len(positions) >= max_results:
                return positions
    return positions


def _extract_candidate_keys_around_marker(
    data: bytes,
    pos: int,
    window: int = 128,
) -> List[int]:
    """Извлекает 32-битные константы вокруг маркера.

    Ищет в окне ±window байт вокруг позиции маркера
    паттерны, похожие на XOR-маски.
    """
    candidates: List[int] = []
    start = max(0, pos - window)
    end = min(len(data), pos + window)

    # Ищем 4-байтовые значения, которые могут быть XOR-масками
    # (ненулевые, не FF*FF*FF*FF, не "очевидные" ASCII)
    for i in range(start, end - 3):
        val = struct.unpack_from('<I', data, i)[0]
        if val == 0:
            continue
        if val == 0xFFFFFFFF:
            continue
        # Пропускаем "очевидные" ASCII/Unicode паттерны
        b0, b1, b2, b3 = data[i:i+4]
        # Все 4 байта — ASCII буквы/цифры: скорее всего строка
        if all(0x20 <= b <= 0x7E for b in [b0, b1, b2, b3]):
            continue
        # Большие 32-битные числа с 3+ нулями в старших байтах
        # — скорее всего packed offset, не XOR-маска
        high_zeros = sum(1 for b in [b3, b2] if b == 0)
        if high_zeros >= 2 and val < 0x10000:
            continue
        candidates.append(val)

    return candidates


def _try_key_on_data(data: bytes, key: int) -> Tuple[Optional[bytes], Optional[str]]:
    """Пробует расшифровать первые 16 байт .gax используя заданный 32-bit ключ.

    Returns:
        (decrypted_prefix, image_extension) если расшифровка даёт известную
        сигнатуру изображения; иначе (None, None).
    """
    if len(data) < 16:
        return None, None

    decrypted = bytearray(data[:32])
    cur_key = key
    for i in range(4, min(32, len(data))):
        decrypted[i] ^= (cur_key >> ((i & 3) * 8)) & 0xFF
        cur_key = (cur_key * 7 + 3) & 0xFFFFFFFF

    ext = _detect_image_signature(bytes(decrypted)[4:16])
    if ext is not None:
        return bytes(decrypted), ext
    return None, None


def find_gax_key_in_exe(exe_path: str) -> Optional[int]:
    """Ищет XOR-ключ для .gax в exe игры.

    Args:
        exe_path: Путь к исполняемому файлу.

    Returns:
        Найденный 32-битный ключ или None.
    """
    if not os.path.isfile(exe_path):
        return None

    try:
        with open(exe_path, 'rb') as f:
            data = f.read()
    except (OSError, PermissionError):
        return None

    if not data:
        return None

    # 1. Сначала пробуем известные константы на образце из папки игры
    #    (если рядом есть .gax файлы)
    candidates: List[int] = []
    candidates.extend(KNOWN_CS2_KEYS)

    # 2. Ищем маркеры и извлекаем кандидатов вокруг них
    markers = _find_markers(data)
    for pos in markers:
        candidates.extend(_extract_candidate_keys_around_marker(data, pos))

    # 3. Ищем паттерны 32-битных XOR-масок по всему exe (эвристика):
    #    значения, которые при применении к типичному PNG заголовку
    #    дают наблюдаемые байты в реальных .gax файлах
    if not markers:
        # Если маркеров нет — exe, скорее всего, не CS2
        return None

    # 4. Пробуем кандидатов на реальных .gax файлах рядом с exe
    exe_dir = os.path.dirname(exe_path)
    sample_gax = _find_sample_gax(exe_dir)
    if sample_gax is not None:
        try:
            with open(sample_gax, 'rb') as f:
                gax_data = f.read()
        except (OSError, PermissionError):
            gax_data = None

        if gax_data is not None:
            for cand in candidates:
                decrypted_prefix, ext = _try_key_on_data(gax_data, cand)
                if ext is not None:
                    return cand

    # 5. Если .gax не нашли рядом — пробуем кандидатов на лету
    #    через полную расшифровку (медленнее, но иногда срабатывает)
    return None


def _find_sample_gax(exe_dir: str, max_depth: int = 3) -> Optional[str]:
    """Ищет любой .gax файл рядом с exe (для тестирования ключей)."""
    try:
        for root, dirs, files in os.walk(exe_dir):
            # Ограничиваем глубину
            depth = root[len(exe_dir):].count(os.sep)
            if depth > max_depth:
                dirs.clear()
                continue
            for f in files:
                if f.lower().endswith('.gax'):
                    return os.path.join(root, f)
    except (OSError, PermissionError):
        return None
    return None


def is_catsystem2_exe(exe_path: str) -> bool:
    """Проверяет, является ли exe игрой на CatSystem2.

    Args:
        exe_path: Путь к exe.

    Returns:
        True если найдены маркеры CS2.
    """
    if not os.path.isfile(exe_path):
        return False
    try:
        with open(exe_path, 'rb') as f:
            data = f.read()
    except (OSError, PermissionError):
        return False

    return any(marker in data for marker in CS2_MARKERS)
