# RPA Extractor

[🇷🇺 Русский](#русский) | [🇬🇧 English](#english)

---

## Русский

**RPA Extractor** — это утилита для распаковки файлов `.rpa` (архивы ресурсов движка Ren'Py) с графическим интерфейсом и CLI.

### Особенности (v0.9.0)
- **Поддержка Drag&Drop**: перетаскивайте `.rpa` файлы или папки с игрой прямо в окно.
- **Автодетект папки с игрой**: новая кнопка «Папка» сканирует директорию и автоматически находит все `.rpa` архивы.
- **GUI и CLI**: используйте GUI для удобства, CLI для автоматизации.
- **Поддержка форматов**: `RPA-2.0`, `RPA-3.0`, `RPA-3.2`.
- **Mass extraction**: распаковка нескольких `.rpa` файлов в один запуск.
- **Long path support (Windows)**: обход лимита 260 символов для путей через префикс `\\?\`.
- **Sanitization**: автоматическая замена недопустимых символов в именах файлов.
- **Path traversal protection**: защита от извлечения файлов вне указанной папки.
- **Двуязычный интерфейс**: переключение между русским и английским на лету.
- **Standalone**: один `.exe` файл, не требует Python.

### Установка
1. Скачайте `RPAExtractor-v0.9.0-windows.zip` из [Releases](https://github.com/Pofium/rpa-ex/releases).
2. Распакуйте в любую папку.
3. Запустите `RPAExtractor.exe`.

### Использование GUI
1. Запустите `RPAExtractor.exe`.
2. Перетащите `.rpa` файл или папку с игрой в окно, либо нажмите «Обзор...» / «Папка».
3. При необходимости измените путь распаковки.
4. Нажмите «Распаковать».

### Использование CLI
```bash
# Распаковать один файл
RPAExtractor.exe file.rpa -o output_dir

# Распаковать все .rpa из папки (автодетект)
RPAExtractor.exe C:\Games\MyGame -o C:\Extracted --auto-detect

# Строгий режим (без continue-on-error)
RPAExtractor.exe file.rpa -o output --strict

# Без санитизации имён
RPAExtractor.exe file.rpa -o output --no-sanitize

# Версия
RPAExtractor.exe --version
```

### Запуск тестов
```bash
python run_tests.py
```

### Сборка из исходников
```bash
pip install -r requirements.txt
pyinstaller rpa_extractor.spec --clean
```

---

## English

**RPA Extractor** — utility for extracting `.rpa` files (Ren'Py engine resource archives) with GUI and CLI.

### Features (v0.9.0)
- **Drag&Drop support**: drop `.rpa` files or game folders directly into the window.
- **Folder auto-detect**: new "Folder" button scans a directory and finds all `.rpa` archives automatically.
- **GUI and CLI**: use GUI for convenience, CLI for automation.
- **Format support**: `RPA-2.0`, `RPA-3.0`, `RPA-3.2`.
- **Mass extraction**: unpack multiple `.rpa` files in a single run.
- **Long path support (Windows)**: bypass 260-char path limit via `\\?\` prefix.
- **Sanitization**: automatically replace invalid characters in filenames.
- **Path traversal protection**: prevents extraction outside the chosen folder.
- **Bilingual interface**: switch between Russian and English on the fly.
- **Standalone**: single `.exe` file, no Python required.

### Installation
1. Download `RPAExtractor-v0.9.0-windows.zip` from [Releases](https://github.com/Pofium/rpa-ex/releases).
2. Extract to any folder.
3. Run `RPAExtractor.exe`.

### GUI usage
1. Run `RPAExtractor.exe`.
2. Drag a `.rpa` file or game folder into the window, or click "Browse..." / "Folder".
3. Optionally change the output path.
4. Click "Extract".

### CLI usage
```bash
# Extract a single file
RPAExtractor.exe file.rpa -o output_dir

# Extract all .rpa from a folder (auto-detect)
RPAExtractor.exe C:\Games\MyGame -o C:\Extracted --auto-detect

# Strict mode (no continue-on-error)
RPAExtractor.exe file.rpa -o output --strict

# Disable name sanitization
RPAExtractor.exe file.rpa -o output --no-sanitize

# Show version
RPAExtractor.exe --version
```

### Running tests
```bash
python run_tests.py
```

### Build from source
```bash
pip install -r requirements.txt
pyinstaller rpa_extractor.spec --clean
```
