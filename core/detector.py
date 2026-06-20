"""Автоопределение формата игровых ассетов."""
import os
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional


class GameFormat(Enum):
    UNKNOWN = "unknown"
    RENPY_RPA = "renpy_rpa"
    RENPY_FOLDER = "renpy_folder"
    UNITY_ASSET = "unity_asset"  # Unity .assets / .bundle / .unity3d
    KIRIKIRI_XP3 = "kirikiri_xp3"  # KiriKiri / 吉里吉里 .xp3 archive
    RPG_MAKER_RGSSAD = "rpg_maker_rgssad"  # RPG Maker XP .rgssad
    RPG_MAKER_RGSS2A = "rpg_maker_rgss2a"  # RPG Maker VX .rgss2a
    RPG_MAKER_RGSS3A = "rpg_maker_rgss3a"  # RPG Maker VX Ace .rgss3a
    RPG_MAKER_MV = "rpg_maker_mv"  # RPG Maker MV/MZ .rpgmvp/.rpgmvo/.rpgmvm
    TELLTALE_TTARCH = "telltale_ttarch"  # Telltale .ttarch
    WOLF_RPG = "wolf_rpg"  # Wolf RPG Editor .wolf
    UNREAL_PAK = "unreal_pak"  # Unreal Engine .pak
    GODOT_PCK = "godot_pck"  # Godot Engine .pck
    CATSYSTEM2_GAX = "catsystem2_gax"  # CatSystem2 .gax (戯画)
    GENERIC_7ZIP = "generic_7zip"  # 7-Zip fallback
    MIXED = "mixed"  # одновременно несколько движков


@dataclass
class AssetInfo:
    path: str
    size: int = 0
    format: GameFormat = GameFormat.UNKNOWN


@dataclass
class GameInfo:
    format: GameFormat
    name: str
    path: str
    assets: List[AssetInfo] = field(default_factory=list)
    total_size: int = 0

    @property
    def total_files(self) -> int:
        return len(self.assets)


class FormatDetector:
    """Детектор форматов игровых ассетов."""

    RPA_HEADER = b'RPA-'
    XP3_MAGIC = b'XP3\r\n \n\x1a\x8b\x67\x01'  # KiriKiri archive
    RGSS1A_MAGIC = b'RGSSAD'
    RGSS2A_MAGIC = b'RGSS2A'
    RGSS3A_MAGIC = b'RGSS3A'
    RPGMV_FAKE_HEADER = b'RPGMV'
    TTARCH_MAGIC = b'TTarch'
    PAK_MAGIC = b'PAK\x00'
    GDPC_MAGIC = b'GDPC'
    GAX_MAGIC = b'\x00\x00\x00\x01'
    RENPY_EXECUTABLES = {'renpy', 'renpy.exe', 'renpy32.exe', 'renpy64.exe'}
    MAX_HEADER_CHECK = 1024

    def detect_file(self, filepath: str) -> GameFormat:
        """Определяет формат одного файла по его заголовку."""
        if not os.path.isfile(filepath):
            return GameFormat.UNKNOWN

        ext = os.path.splitext(filepath)[1].lower()

        try:
            with open(filepath, 'rb') as f:
                header = f.read(self.MAX_HEADER_CHECK)
        except (OSError, PermissionError):
            return GameFormat.UNKNOWN

        if header.startswith(self.RPA_HEADER):
            return GameFormat.RENPY_RPA

        if header.startswith(self.XP3_MAGIC):
            return GameFormat.KIRIKIRI_XP3

        # RPG Maker XP/VX/VX Ace
        if ext == '.rgssad' and header.startswith(self.RGSS1A_MAGIC):
            return GameFormat.RPG_MAKER_RGSSAD
        if ext == '.rgss2a' and header.startswith(self.RGSS2A_MAGIC):
            return GameFormat.RPG_MAKER_RGSS2A
        if ext == '.rgss3a' and header.startswith(self.RGSS3A_MAGIC):
            return GameFormat.RPG_MAKER_RGSS3A

        # RPG Maker MV/MZ encrypted resources
        if ext in ('.rpgmvp', '.png_', '.rpgmvo', '.ogg_', '.rpgmvm', '.m4a_'):
            if header.startswith(self.RPGMV_FAKE_HEADER):
                return GameFormat.RPG_MAKER_MV

        # Telltale TTarch
        if ext == '.ttarch' and header.startswith(self.TTARCH_MAGIC):
            return GameFormat.TELLTALE_TTARCH

        # Unreal PAK
        if ext == '.pak' and header.startswith(self.PAK_MAGIC):
            return GameFormat.UNREAL_PAK

        # Godot PCK
        if ext == '.pck':
            if header.startswith(self.GDPC_MAGIC):
                return GameFormat.GODOT_PCK
            try:
                fsize = os.path.getsize(filepath)
                if fsize > 4:
                    with open(filepath, 'rb') as f2:
                        f2.seek(-4, 2)
                        tail_magic = f2.read(4)
                    if tail_magic == self.GDPC_MAGIC:
                        return GameFormat.GODOT_PCK
            except OSError:
                pass

        # CatSystem2 .gax
        if ext == '.gax' and header.startswith(self.GAX_MAGIC):
            return GameFormat.CATSYSTEM2_GAX

        # UnityFS bundle
        if header.startswith(b'UnityFS'):
            return GameFormat.UNITY_ASSET

        # Старый Unity Asset Bundle
        if len(header) > 4 and header[:4] in (b'\x00\x00\x00\x1c', b'\x00\x00\x00\x0c'):
            return GameFormat.UNITY_ASSET

        # Generic 7-Zip fallback (по расширению)
        if ext in ('.7z', '.zip', '.rar', '.tar', '.gz', '.bz2', '.xz',
                   '.lzma', '.cab', '.iso', '.msi'):
            return GameFormat.GENERIC_7ZIP

        return GameFormat.UNKNOWN

    def detect_folder(self, folder: str) -> GameInfo:
        """Сканирует папку с игрой (рекурсивно) и возвращает список найденных архивов."""
        if not os.path.isdir(folder):
            return GameInfo(
                format=GameFormat.UNKNOWN,
                name=os.path.basename(folder or ''),
                path=folder or '',
            )

        name = os.path.basename(os.path.abspath(folder))
        assets: List[AssetInfo] = []
        total_size = 0
        is_renpy = False

        for root, _dirs, files in os.walk(folder):
            dirs_to_skip = []
            for d in _dirs:
                dl = d.lower()
                if dl in ('__pycache__', '.git', 'node_modules'):
                    dirs_to_skip.append(d)
            for d in dirs_to_skip:
                _dirs.remove(d)

            for filename in files:
                full_path = os.path.join(root, filename)
                try:
                    size = os.path.getsize(full_path)
                except OSError:
                    continue

                fl = filename.lower()

                if fl in ('renpy', 'renpy.exe', 'renpy32.exe', 'renpy64.exe'):
                    is_renpy = True
                    continue

                if fl.endswith('.manifest'):
                    continue

                # Ren'Py .rpa
                if fl.endswith('.rpa'):
                    assets.append(AssetInfo(
                        path=full_path, size=size,
                        format=self.detect_file(full_path),
                    ))
                    total_size += size
                    continue

                # KiriKiri .xp3
                if fl.endswith('.xp3'):
                    fmt = self.detect_file(full_path)
                    if fmt == GameFormat.KIRIKIRI_XP3:
                        assets.append(AssetInfo(
                            path=full_path, size=size, format=GameFormat.KIRIKIRI_XP3,
                        ))
                        total_size += size
                    continue

                # RPG Maker XP/VX/VX Ace
                if fl.endswith(('.rgssad', '.rgss2a', '.rgss3a')):
                    fmt = self.detect_file(full_path)
                    if fmt in (GameFormat.RPG_MAKER_RGSSAD, GameFormat.RPG_MAKER_RGSS2A,
                               GameFormat.RPG_MAKER_RGSS3A):
                        assets.append(AssetInfo(
                            path=full_path, size=size, format=fmt,
                        ))
                        total_size += size
                    continue

                # RPG Maker MV/MZ encrypted resources
                if fl.endswith(('.rpgmvp', '.png_', '.rpgmvo', '.ogg_',
                                '.rpgmvm', '.m4a_')):
                    fmt = self.detect_file(full_path)
                    if fmt == GameFormat.RPG_MAKER_MV:
                        assets.append(AssetInfo(
                            path=full_path, size=size, format=GameFormat.RPG_MAKER_MV,
                        ))
                        total_size += size
                    continue

                # Telltale
                if fl.endswith('.ttarch'):
                    fmt = self.detect_file(full_path)
                    if fmt == GameFormat.TELLTALE_TTARCH:
                        assets.append(AssetInfo(
                            path=full_path, size=size, format=GameFormat.TELLTALE_TTARCH,
                        ))
                        total_size += size
                    continue

                # Unreal PAK
                if fl.endswith('.pak'):
                    fmt = self.detect_file(full_path)
                    if fmt == GameFormat.UNREAL_PAK:
                        assets.append(AssetInfo(
                            path=full_path, size=size, format=GameFormat.UNREAL_PAK,
                        ))
                        total_size += size
                    continue

                # Godot PCK
                if fl.endswith('.pck'):
                    fmt = self.detect_file(full_path)
                    if fmt == GameFormat.GODOT_PCK:
                        assets.append(AssetInfo(
                            path=full_path, size=size, format=GameFormat.GODOT_PCK,
                        ))
                        total_size += size
                    continue

                # CatSystem2 .gax
                if fl.endswith('.gax'):
                    fmt = self.detect_file(full_path)
                    if fmt == GameFormat.CATSYSTEM2_GAX:
                        assets.append(AssetInfo(
                            path=full_path, size=size, format=GameFormat.CATSYSTEM2_GAX,
                        ))
                        total_size += size
                    continue

                # Wolf RPG
                if fl.endswith('.wolf'):
                    assets.append(AssetInfo(
                        path=full_path, size=size, format=GameFormat.WOLF_RPG,
                    ))
                    total_size += size
                    continue

                # Unity files
                is_unity = False
                if fl.endswith(('.assets', '.bundle', '.unity3d', '.resource', '.resS')):
                    is_unity = True
                elif '.' not in filename and (
                    fl.startswith('level') or fl.startswith('globalgamemanagers')
                    or fl.startswith('unity') or fl == 'app.info' or fl == 'boot.config'
                ):
                    is_unity = True
                else:
                    fmt = self.detect_file(full_path)
                    if fmt == GameFormat.UNITY_ASSET:
                        is_unity = True

                if is_unity:
                    assets.append(AssetInfo(
                        path=full_path, size=size, format=GameFormat.UNITY_ASSET,
                    ))
                    total_size += size

        # Итоговый формат
        has_rpa = any(a.format == GameFormat.RENPY_RPA for a in assets)
        has_unity = any(a.format == GameFormat.UNITY_ASSET for a in assets)
        has_xp3 = any(a.format == GameFormat.KIRIKIRI_XP3 for a in assets)
        has_rpgm = any(a.format in (GameFormat.RPG_MAKER_RGSSAD, GameFormat.RPG_MAKER_RGSS2A,
                                    GameFormat.RPG_MAKER_RGSS3A, GameFormat.RPG_MAKER_MV)
                       for a in assets)
        has_ttarch = any(a.format == GameFormat.TELLTALE_TTARCH for a in assets)
        has_pak = any(a.format == GameFormat.UNREAL_PAK for a in assets)
        has_pck = any(a.format == GameFormat.GODOT_PCK for a in assets)
        has_gax = any(a.format == GameFormat.CATSYSTEM2_GAX for a in assets)
        has_wolf = any(a.format == GameFormat.WOLF_RPG for a in assets)

        format_count = sum([
            has_rpa, has_unity, has_xp3, has_rpgm, has_ttarch,
            has_pak, has_pck, has_gax, has_wolf,
        ])
        is_mixed = format_count > 1

        if has_xp3 and not is_mixed:
            fmt = GameFormat.KIRIKIRI_XP3
        elif has_rpgm and not is_mixed:
            fmt = next(
                (a.format for a in assets if a.format in (
                    GameFormat.RPG_MAKER_RGSSAD, GameFormat.RPG_MAKER_RGSS2A,
                    GameFormat.RPG_MAKER_RGSS3A, GameFormat.RPG_MAKER_MV,
                )),
                GameFormat.RPG_MAKER_MV,
            )
        elif has_ttarch and not is_mixed:
            fmt = GameFormat.TELLTALE_TTARCH
        elif has_pak and not is_mixed:
            fmt = GameFormat.UNREAL_PAK
        elif has_pck and not is_mixed:
            fmt = GameFormat.GODOT_PCK
        elif has_gax and not is_mixed:
            fmt = GameFormat.CATSYSTEM2_GAX
        elif has_wolf and not is_mixed:
            fmt = GameFormat.WOLF_RPG
        elif has_rpa and has_unity:
            fmt = GameFormat.MIXED
        elif has_rpa:
            fmt = GameFormat.RENPY_RPA
        elif has_unity:
            fmt = GameFormat.UNITY_ASSET
        elif is_renpy:
            fmt = GameFormat.RENPY_FOLDER
        elif is_mixed:
            fmt = GameFormat.MIXED
        else:
            fmt = GameFormat.UNKNOWN

        return GameInfo(
            format=fmt,
            name=name,
            path=folder,
            assets=assets,
            total_size=total_size,
        )

    def collect_rpa_files(self, target: str) -> List[AssetInfo]:
        """Возвращает все .rpa файлы из target (файл или папка)."""
        if os.path.isfile(target):
            if target.lower().endswith('.rpa'):
                fmt = self.detect_file(target)
                if fmt == GameFormat.RENPY_RPA:
                    return [AssetInfo(
                        path=target,
                        size=os.path.getsize(target),
                        format=fmt,
                    )]
            return []

        if os.path.isdir(target):
            info = self.detect_folder(target)
            return info.assets

        return []
