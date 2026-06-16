"""Пакет распаковщиков для разных форматов игровых ассетов."""
from .rpa_unpacker import RpaUnpacker

__all__ = ['RpaUnpacker']

# UnityUnpacker импортируется опционально (нужен UnityPy)
try:
    from .unity_unpacker import UnityUnpacker
    __all__.append('UnityUnpacker')
except ImportError:
    UnityUnpacker = None
