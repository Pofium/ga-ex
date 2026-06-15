"""Автоопределение формата игровых ассетов."""
import os
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional


class GameFormat(Enum):
    UNKNOWN = "unknown"
    RENPY_RPA = "renpy_rpa"
    RENPY_FOLDER = "renpy_folder"


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
    """Детектор форматов Ren'Py/RPA и папок с игрой."""

    RPA_HEADER = b'RPA-'
    RENPY_EXECUTABLES = {'renpy', 'renpy.exe', 'renpy32.exe', 'renpy64.exe'}
    MAX_HEADER_CHECK = 1024

    def detect_file(self, filepath: str) -> GameFormat:
        """Определяет формат одного файла по его заголовку."""
        if not os.path.isfile(filepath):
            return GameFormat.UNKNOWN

        try:
            with open(filepath, 'rb') as f:
                header = f.read(self.MAX_HEADER_CHECK)
        except (OSError, PermissionError):
            return GameFormat.UNKNOWN

        if header.startswith(self.RPA_HEADER):
            return GameFormat.RENPY_RPA

        return GameFormat.UNKNOWN

    def detect_folder(self, folder: str) -> GameInfo:
        """Сканирует папку с игрой и возвращает список найденных .rpa."""
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
            for filename in files:
                full_path = os.path.join(root, filename)
                try:
                    size = os.path.getsize(full_path)
                except OSError:
                    continue

                if filename.lower() == 'renpy' or filename.lower() in self.RENPY_EXECUTABLES:
                    is_renpy = True
                    continue

                if filename.lower().endswith('.rpa'):
                    assets.append(AssetInfo(
                        path=full_path,
                        size=size,
                        format=self.detect_file(full_path),
                    ))
                    total_size += size

        if is_renpy or assets:
            fmt = GameFormat.RENPY_RPA if assets else GameFormat.RENPY_FOLDER
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
