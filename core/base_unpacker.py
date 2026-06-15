"""Базовый класс для всех распаковщиков игровых ассетов."""
from abc import ABC, abstractmethod
from typing import Callable, Optional, List
from dataclasses import dataclass, field


@dataclass
class UnpackOptions:
    """Параметры распаковки."""
    output_dir: str
    sanitize_names: bool = True
    continue_on_error: bool = True
    use_long_paths: bool = True
    overwrite: bool = False
    create_subdirs: bool = True


@dataclass
class UnpackResult:
    """Результат распаковки."""
    success: bool
    files_extracted: List[str] = field(default_factory=list)
    skipped: List[dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    output_dir: str = ''


ProgressCallback = Callable[[str, int, int], None]


class BaseUnpacker(ABC):
    """Абстрактный распаковщик."""

    name: str = 'base'

    @abstractmethod
    def detect(self, target: str) -> bool:
        """Проверяет, может ли обработать указанный файл или папку."""
        pass

    @abstractmethod
    def analyze(self, target: str) -> dict:
        """Анализирует цель и возвращает метаданные (количество, размер)."""
        pass

    @abstractmethod
    def unpack(
        self,
        target: str,
        options: UnpackOptions,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> UnpackResult:
        """Распаковывает ассеты."""
        pass
