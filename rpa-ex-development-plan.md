# План развития rpa-ex: от v0.8.4 к мультиформатному распаковщику

## Текущее состояние проекта (v0.8.4)

**Реализовано:**
- ✅ GUI на PySide6 с Drag&Drop для `.rpa` файлов
- ✅ Массовая распаковка нескольких архивов
- ✅ Поддержка RPA-2.0, RPA-3.0, RPA-3.2 (с динамическим XOR-ключом)
- ✅ Long path support Windows (префикс `\\?\`)
- ✅ Санитизация недопустимых символов и зарезервированных имён
- ✅ Защита от path traversal
- ✅ Двуязычный интерфейс RU/EN
- ✅ Сохранение настроек через QSettings
- ✅ Иконка приложения, .exe через PyInstaller
- ✅ Релиз v0.8.4 на GitHub (Pofium/rpa-ex)

**Структура:**
```
c:\Projects\rpa-ex\
├── app.py                       # Точка входа QApplication
├── core/
│   ├── errors.py                # Типы ошибок
│   ├── extractor.py             # RpaExtractor + sanitize_filename + long paths
│   └── rpa_reader.py            # Чтение заголовка, индекса, entries
├── ui/
│   ├── i18n.py                  # Словарь RU/EN + I18n класс
│   └── main_window.py           # MainWindow + ExtractThread + DropZone
├── .github/
│   ├── ISSUE_TEMPLATE/          # bug, feature, rpa variant
│   └── workflows/build.yml      # CI для Windows
├── icon.ico                     # Иконка
├── rpa_extractor.spec           # PyInstaller spec
├── requirements.txt             # PySide6, pyinstaller
├── CHANGELOG.md                 # История версий
├── README.md                    # Двуязычное описание
└── release-notes.md             # Шаблон для релизов
```

## Цели нового этапа (v0.9.0+)

### 🎯 Стратегические цели
1. **Расширение форматов**: поддержка RPA-1.0, улучшенная поддержка edge-кейсов
2. **Folder-based mode**: выбор папки с игрой (а не отдельных файлов) с автоопределением
3. **CLI режим**: для автоматизации и интеграции в скрипты
4. **Тесты**: покрытие критических путей (sanitize, path traversal, long paths)
5. **Производительность**: потоковая запись больших файлов, mmap для индексов

## Архитектура после рефакторинга

### Новая модульная структура

```
rpa-ex/
├── core/
│   ├── errors.py                 # (уже есть) — расширить typed exceptions
│   ├── rpa_reader.py             # (уже есть)
│   ├── extractor.py              # (уже есть) — вынести в rpa_extractor.py
│   ├── detector.py               # НОВЫЙ: автоопределение формата
│   ├── base_unpacker.py          # НОВЫЙ: ABC для распаковщиков
│   └── progress_tracker.py       # НОВЫЙ: потокобезопасный прогресс
├── unpackers/                    # НОВАЯ ПАПКА
│   └── rpa_unpacker.py           # Обёртка над RpaExtractor, реализует BaseUnpacker
├── ui/
│   ├── main_window.py            # (уже есть) — рефакторинг, добавить folder mode
│   ├── components/               # НОВАЯ ПАПКА
│   │   ├── folder_selector.py
│   │   ├── progress_widget.py
│   │   └── log_viewer.py
│   └── i18n.py                   # (уже есть)
├── tests/                        # НОВАЯ ПАПКА
│   ├── test_rpa_reader.py
│   ├── test_extractor.py
│   ├── test_sanitize.py
│   └── fixtures/                 # Минимальные тестовые .rpa
├── cli.py                        # НОВЫЙ: argparse-based CLI
├── app.py                        # (уже есть)
├── pyproject.toml                # НОВЫЙ: современная конфигурация
└── ... (rpa_extractor.spec, requirements.txt, etc.)
```

## Этап 1: Рефакторинг существующего кода

### 1.1 Переименование extractor.py → rpa_unpacker.py + BaseUnpacker
**Цель:** подготовить почву для добавления других форматов (Unity, обычные архивы).

```python
# core/base_unpacker.py
from abc import ABC, abstractmethod
from typing import Callable, Optional, List
from dataclasses import dataclass

@dataclass
class UnpackOptions:
    output_dir: str
    sanitize_names: bool = True
    continue_on_error: bool = True
    use_long_paths: bool = True
    overwrite: bool = False
    create_subdirs: bool = True

@dataclass
class UnpackResult:
    success: bool
    files_extracted: List[str]
    skipped: List[dict]
    errors: List[str]
    output_dir: str

class BaseUnpacker(ABC):
    @abstractmethod
    def detect(self, target: str) -> bool: ...

    @abstractmethod
    def analyze(self, target: str) -> dict: ...

    @abstractmethod
    def unpack(
        self,
        target: str,
        options: UnpackOptions,
        progress_callback: Optional[Callable] = None
    ) -> UnpackResult: ...
```

### 1.2 FormatDetector
```python
# core/detector.py
from enum import Enum

class GameFormat(Enum):
    UNKNOWN = "unknown"
    RENPY_RPA = "renpy_rpa"
    RENPY_FOLDER = "renpy_folder"

@dataclass
class GameInfo:
    format: GameFormat
    name: str
    path: str
    assets: List[dict]  # файлы с метаданными

class FormatDetector:
    def detect_file(self, filepath: str) -> GameFormat: ...
    def detect_folder(self, folder: str) -> GameInfo: ...
```

## Этап 2: Поддержка новых форматов

### 2.1 RPA-1.0
**Формат:** самый старый вариант, индекс хранится в начале файла.
```python
# core/rpa_reader.py — добавить RPA_10_SIGNATURE = b'RPA-1.0 '
```

### 2.2 Большие архивы
**Проблема:** 4.9 GB `002.rpa` от FalseHero уже решено long paths + continue-on-error.
**Дополнительно:**
- mmap для чтения индекса
- Потоковая запись больших файлов (chunked write)

## Этап 3: Улучшение UI

### 3.1 Folder-based mode
Пользователь может:
- Перетащить папку с игрой → автодетект формата → список `.rpa` файлов
- Или выбрать через диалог

### 3.2 LogViewer
Отдельная панель для просмотра пропущенных файлов с причинами.

### 3.3 История
Сохранение последних 10 путей распаковки в QSettings.

## Этап 4: CLI режим

```bash
rpa-ex.exe "C:\Games\game\images.rpa" -o "C:\output"
rpa-ex.exe "C:\Games\game" --auto-detect
rpa-ex.exe "C:\Games\game\*.rpa" --sanitize --long-paths --continue-on-error
```

## Этап 5: Тестирование

### 5.1 Unit-тесты
- `test_sanitize.py`: проверка замены `<>:"/\|?*`, защита зарезервированных имён
- `test_extractor.py`: path traversal блокируется, long paths работают
- `test_rpa_reader.py`: парсинг заголовков 2.0/3.0/3.2, восстановление после corrupt index

### 5.2 Integration
- `test_extract_real.py`: тестовый минимальный `.rpa` (генерируется в setUp)

## Этап 6: Производительность

- mmap для индексов RPA (вместо полного чтения в RAM)
- Chunked write для файлов >100 MB
- Кеширование QSettings в памяти

## Этап 7: Сборка и релиз v0.9.0

- Обновить версию в `rpa_extractor.spec` (если нужно) и `__init__.py`
- Обновить `CHANGELOG.md`
- Обновить `README.md` с примерами folder mode и CLI
- Собрать EXE через PyInstaller
- Создать релиз v0.9.0 на GitHub с архивом
- Запустить CI через push tag

## План выполнения (по приоритетам)

| # | Задача | Трудоёмкость | Зависит от |
|---|--------|-------------|-----------|
| 1 | BaseUnpacker + перенос extractor.py в rpa_unpacker.py | 2ч | — |
| 2 | FormatDetector для файлов и папок | 2ч | — |
| 3 | Unit-тесты sanitize + path traversal + long paths | 3ч | 1 |
| 4 | Поддержка RPA-1.0 (если встретится) | 1ч | — |
| 5 | Folder-based mode в GUI | 3ч | 1, 2 |
| 6 | LogViewer (просмотр skipped) | 2ч | 1 |
| 7 | CLI режим (argparse) | 2ч | 1, 2 |
| 8 | pyproject.toml вместо requirements.txt | 1ч | — |
| 9 | Сборка EXE + релиз v0.9.0 | 1ч | 1-7 |

## Критерии готовности v0.9.0

- [ ] Drag&Drop папки с игрой → автодетект → список .rpa
- [ ] CLI: `rpa-ex.exe path/to/file.rpa -o output`
- [ ] Все 4 типа опций работают (sanitize, long paths, continue-on-error, overwrite)
- [ ] Минимум 80% покрытия тестами критических путей
- [ ] EXE запускается на чистой Windows-машине
- [ ] Релиз v0.9.0 опубликован с архивом и подробным описанием

---

*Дата: 2026-06-15*
*Версия плана: 3.0 — синхронизирован с реальным состоянием проекта v0.8.4*
