#!/usr/bin/env python3
"""Скрипт переименования проекта RPAExtractor -> GAExtractor.

Заменяет:
- RPAExtractor.exe -> GAExtractor.exe
- RPA Extractor -> GA Extractor
- RPAExtractor -> GAExtractor (идентификаторы, QSettings, application name)
- rpa_extractor.spec -> ga_extractor.spec

Запускать из корня проекта.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(r"C:\Projects\rpa-ex")

# Правила замены: (search, replace, regex_flag)
REPLACEMENTS_TEXT = [
    ('RPAExtractor.exe', 'GAExtractor.exe'),
    ('RPA Extractor', 'GA Extractor'),
    ('RPAExtractor', 'GAExtractor'),
]

# Файлы, которые обновляем по тексту
TEXT_FILES = [
    'app.py',
    'ui/main_window.py',
    'ui/i18n.py',
    'unpackers/unity_unpacker.py',
    'README.md',
    'CHANGELOG.md',
    'rpa-ex-development-plan.md',
    '.github/workflows/build.yml',
]


def update_text_file(path: Path) -> int:
    """Обновляет один файл, возвращая количество замен."""
    if not path.is_file():
        return 0
    text = path.read_text(encoding='utf-8')
    original = text
    count = 0
    for old, new in REPLACEMENTS_TEXT:
        if old in text:
            n = text.count(old)
            text = text.replace(old, new)
            count += n
    if text != original:
        path.write_text(text, encoding='utf-8')
    return count


def rename_spec_file() -> None:
    """Переименовывает spec файл."""
    old = ROOT / 'rpa_extractor.spec'
    new = ROOT / 'ga_extractor.spec'
    if old.exists() and not new.exists():
        old.rename(new)
        print(f'  Renamed: {old.name} -> {new.name}')


def main() -> int:
    print(f'Root: {ROOT}\n')

    total_changes = 0
    print('Updating text files:')
    for rel_path in TEXT_FILES:
        full = ROOT / rel_path
        if not full.exists():
            print(f'  SKIP (not found): {rel_path}')
            continue
        n = update_text_file(full)
        status = f'{n} changes' if n else 'no changes'
        print(f'  {rel_path}: {status}')
        total_changes += n

    print('\nRenaming spec file:')
    rename_spec_file()

    # Также обновим spec файл (теперь ga_extractor.spec)
    spec_path = ROOT / 'ga_extractor.spec'
    if spec_path.exists():
        n = update_text_file(spec_path)
        print(f'  ga_extractor.spec: {n} changes')

    print(f'\nTotal text replacements: {total_changes}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
