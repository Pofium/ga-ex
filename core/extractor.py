"""Backwards-compatible re-export. Реальный код в unpackers/rpa_unpacker.py."""
from unpackers.rpa_unpacker import (
    RpaUnpacker,
    sanitize_filename,
    enable_long_path_support,
    to_extended_path,
    INVALID_FN_CHARS,
    RESERVED_WIN_NAMES,
    PathTraversalError,
)
from core.rpa_reader import RpaReader, RpaEntry

__all__ = [
    'RpaUnpacker',
    'RpaReader',
    'RpaEntry',
    'sanitize_filename',
    'enable_long_path_support',
    'to_extended_path',
    'INVALID_FN_CHARS',
    'RESERVED_WIN_NAMES',
    'PathTraversalError',
]
