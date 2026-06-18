"""Пакет распаковщиков для разных форматов игровых ассетов."""
from .rpa_unpacker import RpaUnpacker
from .unity_unpacker import UnityUnpacker

__all__ = ['RpaUnpacker', 'UnityUnpacker']

# Проверяем наличие UnityPy
try:
    import UnityPy  # noqa: F401
    UNITY_AVAILABLE = True
except ImportError:
    UNITY_AVAILABLE = False
