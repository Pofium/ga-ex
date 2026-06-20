"""Дешифровка RPG Maker MV/MZ зашифрованных ресурсов.

Формат (по https://github.com/petschko/RPG-Maker-MV-Decrypter):
  Encrypted file = [fake_header: 16 байт] + [XORed bytes: headerLen байт] + [raw data]
  fake_header default: signature=5250474d56000000 (RPGMV\0\0\0)
                       version=000301
                       remain=0000000000
  XOR применён только к первым headerLen байтам (по умолчанию 16).
  key = 32 hex символа (16 байт) = пара hex на каждый байт XOR.

No-key PNG recovery (для .rpgmvp):
  Encrypted = [fake_hdr:16] + [XOR(png_hdr, key):16] + [raw PNG body]
  После пропуска первых 32 байт идёт чистый PNG, начинающийся с 16 байт XOR-данных.
  Восстановление: data[32:] + original_png_header (89 50 4E 47 ...).
"""
from __future__ import annotations

import io
import os
import re
import zlib
from typing import Optional, Tuple

# PNG-header (16 байт) — известные первые 16 байт любого валидного PNG
PNG_HEADER_16 = bytes.fromhex('89504E470D0A1A0A0000000D49484452')

# Дефолтные параметры fake-header для RPG Maker MV
DEFAULT_HEADER_LEN = 16
DEFAULT_SIGNATURE = '5250474d56000000'  # "RPGMV\0\0\0"
DEFAULT_VERSION = '000301'
DEFAULT_REMAIN = '0000000000'


class RpgmDecryptError(Exception):
    """Ошибка при дешифровке RPG Maker файла."""


class RpgmDecrypter:
    """Дешифровщик RPG Maker MV/MZ зашифрованных ресурсов.

    Args:
        encryption_key: 32 hex символа (16 байт). Если None — будет попытка
            восстановления PNG без ключа.
        header_len: длина fake-header (по умолчанию 16).
        signature: hex-строка сигнатуры (по умолчанию '5250474d56000000').
        version: hex-строка версии (по умолчанию '000301').
        remain: hex-строка remainder (по умолчанию '0000000000').
        verify_fake_header: проверять ли сигнатуру перед расшифровкой.
    """

    def __init__(
        self,
        encryption_key: Optional[str] = None,
        header_len: int = DEFAULT_HEADER_LEN,
        signature: str = DEFAULT_SIGNATURE,
        version: str = DEFAULT_VERSION,
        remain: str = DEFAULT_REMAIN,
        verify_fake_header: bool = True,
    ) -> None:
        self.header_len = int(header_len)
        self.signature = signature
        self.version = version
        self.remain = remain
        self.verify_fake_header = verify_fake_header
        self.encryption_key = self._normalize_key(encryption_key) if encryption_key else None

    @staticmethod
    def _normalize_key(key: str) -> bytes:
        """Преобразует 32 hex-символа в 16 байт. Бросает ValueError если не hex."""
        # Удаляем все не-hex символы на всякий случай
        clean = re.sub(r'[^0-9a-fA-F]', '', key)
        if len(clean) < 32:
            raise ValueError(f'Encryption key too short: {len(clean)} hex chars (need 32)')
        clean = clean[:32]
        try:
            return bytes.fromhex(clean)
        except ValueError as e:
            raise ValueError(f'Invalid hex in encryption key: {e}') from e

    def build_fake_header(self) -> bytes:
        """Собирает fake-header по сигнатуре/версии/remain."""
        header = (self.signature + self.version + self.remain)[:self.header_len * 2]
        return bytes.fromhex(header.ljust(self.header_len * 2, '0')[:self.header_len * 2])

    def verify_fake_header_in(self, data: bytes) -> bool:
        """Проверяет, что первые header_len байт data совпадают с fake-header."""
        if len(data) < self.header_len:
            return False
        return data[:self.header_len] == self.build_fake_header()

    def decrypt(self, data: bytes) -> bytes:
        """Дешифрует data, убирает fake-header, возвращает расшифрованный контент.

        Raises:
            RpgmDecryptError: при ошибке (например, неверная сигнатура).
        """
        if len(data) < self.header_len:
            raise RpgmDecryptError(
                f'Data too short: {len(data)} < header_len {self.header_len}'
            )
        if not self.encryption_key:
            raise RpgmDecryptError('Encryption key is not set; use restore_png_no_key() for images')

        # 1) Опциональная проверка fake-header
        if self.verify_fake_header and not self.verify_fake_header_in(data):
            raise RpgmDecryptError(
                'Fake-header verification failed (wrong signature/version)'
            )

        # 2) Удаляем fake-header
        body = bytearray(data[self.header_len:])

        # 3) XOR первые self.header_len байт с ключом
        key = self.encryption_key
        n = min(self.header_len, len(body))
        for i in range(n):
            body[i] ^= key[i]

        return bytes(body)

    def decrypt_file(self, filepath: str) -> bytes:
        """Читает файл и расшифровывает."""
        with open(filepath, 'rb') as f:
            data = f.read()
        return self.decrypt(data)

    def encrypt(self, data: bytes) -> bytes:
        """Зашифровывает data с fake-header (обратная операция)."""
        if not self.encryption_key:
            raise RpgmDecryptError('Encryption key is not set')

        # 1) XOR первые self.header_len байт с ключом
        body = bytearray(data)
        key = self.encryption_key
        n = min(self.header_len, len(body))
        for i in range(n):
            body[i] ^= key[i]

        # 2) Prepend fake-header
        result = bytearray()
        result.extend(self.build_fake_header())
        result.extend(body)
        return bytes(result)

    def restore_png_no_key(self, data: bytes) -> bytes:
        """Восстанавливает PNG из .rpgmvp БЕЗ ключа.

        Encrypted = [fake_hdr:16] + [XOR(png_hdr, key):16] + [raw PNG body]
        После первых 32 байт идёт не-encrypted PNG body (но первые 16 байт
        этого body — это XOR(png_header, key), а не сам PNG header).
        Реальный PNG начинается с offset 32, но его первые 16 байт — это
        зашифрованный header. Чтобы получить валидный PNG:
          decrypted_png = original_png_header (16) + data[32:]

        Args:
            data: содержимое .rpgmvp файла.

        Returns:
            Восстановленный PNG-байтовый поток.
        """
        if len(data) < self.header_len * 2:
            raise RpgmDecryptError(
                f'PNG data too short: {len(data)} < {self.header_len * 2}'
            )
        body = data[self.header_len * 2:]
        out = bytearray()
        out.extend(PNG_HEADER_16[:self.header_len])
        out.extend(body)
        return bytes(out)

    def restore_png_no_key_file(self, filepath: str) -> bytes:
        """Читает .rpgmvp и восстанавливает PNG без ключа."""
        with open(filepath, 'rb') as f:
            data = f.read()
        return self.restore_png_no_key(data)


# ============ Key extraction ============

def _read_text(path: str) -> str:
    """Читает файл как текст (с защитой от ошибок декодирования)."""
    with open(path, 'rb') as f:
        raw = f.read()
    return raw.decode('utf-8', errors='replace')


def _try_lzstring_decompress(text: str) -> Optional[str]:
    """Пробует распаковать LZ-String (base64) в строку.

    Pure-Python реализация LZ-String (decode) для формата, используемого RPG Maker.
    Возвращает None если не LZ-String.
    """
    # Импортируем лениво, чтобы не требовать lzstring при базовом использовании
    try:
        import lzstring  # type: ignore
        return lzstring.LZString.decompressFromBase64(text)
    except ImportError:
        return None
    except Exception:
        return None


def extract_key_from_system_json(path: str) -> Optional[str]:
    """Извлекает encryptionKey из System.json (RPG Maker MV/MZ).

    Файл: %PROJECT%/www/data/System.json (MV) или %PROJECT%/data/System.json (MZ).
    Может быть LZ-String сжат.
    """
    if not os.path.isfile(path):
        return None
    text = _read_text(path).strip()
    if not text:
        return None
    # Попытка 1: чистый JSON
    import json
    try:
        data = json.loads(text)
        if isinstance(data, list) and data:
            data = data[0]
        if isinstance(data, dict) and 'encryptionKey' in data:
            return str(data['encryptionKey'])
    except (json.JSONDecodeError, ValueError):
        pass
    # Попытка 2: LZ-String compressed JSON
    decompressed = _try_lzstring_decompress(text)
    if decompressed:
        try:
            data = json.loads(decompressed)
            if isinstance(data, list) and data:
                data = data[0]
            if isinstance(data, dict) and 'encryptionKey' in data:
                return str(data['encryptionKey'])
        except (json.JSONDecodeError, ValueError):
            pass
    # Попытка 3: regex по ключу
    m = re.search(r'"encryptionKey"\s*:\s*"([0-9a-fA-F]{32})"', text)
    if m:
        return m.group(1)
    return None


def extract_key_from_rpg_core_js(path: str) -> Optional[str]:
    """Извлекает encryption key из rpg_core.js.

    MV: %PROJECT%/www/js/rpg_core.js
    MZ: %PROJECT%/js/rpg_core.js
    """
    if not os.path.isfile(path):
        return None
    text = _read_text(path)
    # Попытка 1: this._encryptionKey = "...";
    m = re.search(r'this\._encryptionKey\s*=\s*"([0-9a-fA-F]{32})"', text)
    if m:
        return m.group(1)
    # Попытка 2: Decrypter._encryptionKey = "...";
    m = re.search(r'Decrypter\._encryptionKey\s*=\s*"([0-9a-fA-F]{32})"', text)
    if m:
        return m.group(1)
    # Попытка 3: просто hex 32 chars в кавычках
    m = re.search(r'"([0-9a-fA-F]{32})"', text)
    if m:
        return m.group(1)
    return None


def extract_key_from_rpgmvp(path: str) -> Optional[str]:
    """Извлекает encryption key из .rpgmvp через XOR-анализ.

    Известны первые 16 байт PNG header.
    Encrypted: [fake_hdr:16] + [XOR(png_hdr, key):16] + ...
    data[16:32] = XOR(png_hdr, key)
    png_hdr[0:16] = PNG_HEADER_16[0:16]
    => key[i] = data[16+i] ^ PNG_HEADER_16[i]
    """
    if not os.path.isfile(path):
        return None
    with open(path, 'rb') as f:
        head = f.read(32)
    if len(head) < 32:
        return None
    # Sanity check: первый байт fake_header должен быть 0x52 ('R')
    # Сигнатура RPGMV = 0x52 0x50 0x47 0x4d 0x56
    if head[:5] != b'RPGMV'[:5]:
        # Не RPGMV формат
        return None
    # Извлекаем ключ
    key = bytearray(16)
    for i in range(16):
        key[i] = head[16 + i] ^ PNG_HEADER_16[i]
    return key.hex()


def find_rpg_maker_key(game_dir: str) -> Tuple[Optional[str], str]:
    """Ищет encryption key в стандартных местах RPG Maker MV/MZ.

    Args:
        game_dir: путь к папке игры.

    Returns:
        (key, source) — найденный ключ и описание источника.
        Если не найден: (None, '').
    """
    # Кандидаты для System.json
    sys_candidates = [
        os.path.join(game_dir, 'www', 'data', 'System.json'),
        os.path.join(game_dir, 'data', 'System.json'),
    ]
    for path in sys_candidates:
        key = extract_key_from_system_json(path)
        if key:
            return key, f'System.json: {path}'

    # Кандидаты для rpg_core.js
    core_candidates = [
        os.path.join(game_dir, 'www', 'js', 'rpg_core.js'),
        os.path.join(game_dir, 'js', 'rpg_core.js'),
    ]
    for path in core_candidates:
        key = extract_key_from_rpg_core_js(path)
        if key:
            return key, f'rpg_core.js: {path}'

    # Поиск System.json / rpg_core.js рекурсивно (вдруг нестандартная структура)
    for root, _dirs, files in os.walk(game_dir):
        # Ограничиваем глубину
        depth = root[len(game_dir):].count(os.sep)
        if depth > 3:
            continue
        for f in files:
            full = os.path.join(root, f)
            if f.lower() == 'system.json':
                key = extract_key_from_system_json(full)
                if key:
                    return key, f'System.json: {full}'
            elif f.lower() == 'rpg_core.js':
                key = extract_key_from_rpg_core_js(full)
                if key:
                    return key, f'rpg_core.js: {full}'

    return None, ''
