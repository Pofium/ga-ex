# GA Extractor

[🇷🇺 Русский](#русский) | [🇬🇧 English](#english)

---

## Русский

**GA Extractor** (Game Archive Extractor) — это утилита для распаковки архивов
ресурсов из игр на различных движках с графическим интерфейсом и CLI.

### Поддерживаемые форматы (v0.12.0)

| Движок | Расширения | Распаковка |
|---|---|---|
| **Ren'Py** | `.rpa` (2.0/3.0/3.2) | ✅ Полная |
| **Unity** | `.assets`, `.bundle`, `.unity3d`, `.resource`, `.resS` | ✅ Полная (UnityPy) |
| **KiriKiri** | `.xp3` | ✅ Полная |
| **RPG Maker XP/VX/VX Ace** | `.rgssad`, `.rgss2a`, `.rgss3a` | ✅ Полная |
| **RPG Maker MV/MZ** | `.rpgmvp`, `.rpgmvo`, `.rpgmvm`, `.png_`, `.ogg_`, `.m4a_` | ✅ Полная (с ключом) |
| **CatSystem2** | `.gax`, `.pck` | ⚠️ Частично (см. ниже) |
| **Telltale** | `.ttarch` | 🔍 Детект |
| **Wolf RPG Editor** | `.wolf` | 🔍 Детект |
| **Unreal Engine** | `.pak` | 🔍 Детект |
| **Godot Engine** | `.pck` | 🔍 Детект |
| **7-Zip fallback** | `.7z`, `.zip`, `.rar`, `.tar`, `.gz`, `.bz2`, `.xz` | ✅ Полная (через 7z CLI) |

### Особенности

- **Поддержка Drag&Drop**: перетаскивайте файлы или папки прямо в окно.
- **Автодетект папки с игрой**: кнопка «Папка» сканирует директорию.
- **Поле EXE для .gax**: опционально. Укажите путь к exe игры — GAExtractor попробует
  извлечь ключ шифрования по маркерам CS2. **Важно:** CatSystem2 использует
  per-game шифрование; для некоторых игр (например, *Kabe no Mukou no Tsuma no Koe 3*)
  смещение ключа в exe захардкожено и не может быть найдено универсально — см. раздел
  «Расшифровка CatSystem2 .gax» ниже.
- **GUI и CLI**: используйте GUI для удобства, CLI для автоматизации.
- **Mass extraction**: распаковка нескольких архивов в один запуск.
- **Long path support (Windows)**: обход лимита 260 символов через `\\?\` префикс.
- **Sanitization**: автоматическая замена недопустимых символов в именах файлов.
- **Path traversal protection**: защита от извлечения файлов вне указанной папки.
- **Двуязычный интерфейс**: переключение между русским и английским на лету.
- **Standalone**: один `.exe` файл, не требует Python.

### Установка

1. Скачайте `GAExtractor.exe` из [Releases](https://github.com/Pofium/rpa-ex/releases/tag/v0.12.0).
2. Запустите `GAExtractor.exe` — установка не требуется.

> Опционально: для распаковки `.7z`, `.rar`, `.tar.gz` и других архивов установите [7-Zip](https://www.7-zip.org/).

### Использование GUI

1. Запустите `GAExtractor.exe`.
2. Перетащите архивы (`.rpa`, `.xp3`, `.assets`, `.rgssad`, `.gax`, ...) или папку с игрой
   в окно, либо нажмите «Обзор...» / «Папка».
3. **Для .gax (CatSystem2)**: укажите путь к exe игры в поле «EXE (для .gax)».
4. При необходимости измените путь распаковки.
5. Нажмите «Распаковать».

### Использование CLI

```bash
# Распаковать один файл (формат определяется автоматически)
GAExtractor.exe file.rpa -o output_dir
GAExtractor.exe game.xp3 -o output_dir
GAExtractor.exe Game.rgss3a -o output_dir

# Распаковать все архивы из папки (автодетект)
GAExtractor.exe C:\Games\MyGame -o C:\Extracted --auto-detect

# Строгий режим (без continue-on-error)
GAExtractor.exe file.rpa -o output --strict

# Без санитизации имён
GAExtractor.exe file.rpa -o output --no-sanitize

# Версия
GAExtractor.exe --version
```

### Запуск тестов

```bash
python run_tests.py
```

### Сборка из исходников

```bash
pip install -r requirements.txt
pyinstaller ga_extractor.spec --clean
```

Результат: `dist/GAExtractor.exe` (~280 MB, standalone).

---

## English

**GA Extractor** (Game Archive Extractor) — utility for unpacking resource archives
from games built with various engines, with both GUI and CLI.

### Supported formats (v0.12.0)

| Engine | Extensions | Unpacking |
|---|---|---|
| **Ren'Py** | `.rpa` (2.0/3.0/3.2) | ✅ Full |
| **Unity** | `.assets`, `.bundle`, `.unity3d`, `.resource`, `.resS` | ✅ Full (UnityPy) |
| **KiriKiri** | `.xp3` | ✅ Full |
| **RPG Maker XP/VX/VX Ace** | `.rgssad`, `.rgss2a`, `.rgss3a` | ✅ Full |
| **RPG Maker MV/MZ** | `.rpgmvp`, `.rpgmvo`, `.rpgmvm`, `.png_`, `.ogg_`, `.m4a_` | ✅ Full (with key) |
| **CatSystem2** | `.gax`, `.pck` | ⚠️ Detect + decrypt (with game exe) |
| **Telltale** | `.ttarch` | 🔍 Detect |
| **Wolf RPG Editor** | `.wolf` | 🔍 Detect |
| **Unreal Engine** | `.pak` | 🔍 Detect |
| **Godot Engine** | `.pck` | 🔍 Detect |
| **7-Zip fallback** | `.7z`, `.zip`, `.rar`, `.tar`, `.gz`, `.bz2`, `.xz` | ✅ Full (via 7z CLI) |

### Features

- **Drag&Drop support**: drop files or game folders directly into the window.
- **Folder auto-detect**: "Folder" button scans a directory and finds all archives.
- **EXE field for .gax**: optional. Specify the path to the game exe — GAExtractor
  will try to extract the encryption key by searching for CS2 markers. **Note:**
  CatSystem2 uses per-game encryption; for some games (e.g. *Kabe no Mukou no
  Tsuma no Koe 3*) the key offset in the exe is hardcoded and cannot be found
  generically — see "CatSystem2 .gax decryption" below for details.
- **GUI and CLI**: use GUI for convenience, CLI for automation.
- **Mass extraction**: unpack multiple archives in a single run.
- **Long path support (Windows)**: bypass 260-char path limit via `\\?\` prefix.
- **Sanitization**: automatically replace invalid characters in filenames.
- **Path traversal protection**: prevents extraction outside the chosen folder.
- **Bilingual interface**: switch between Russian and English on the fly.
- **Standalone**: single `.exe` file, no Python required.

### Installation

1. Download `GAExtractor.exe` from [Releases](https://github.com/Pofium/rpa-ex/releases/tag/v0.12.0).
2. Run `GAExtractor.exe` — no installation required.

> Optional: for `.7z`, `.rar`, `.tar.gz` etc. install [7-Zip](https://www.7-zip.org/).

### GUI usage

1. Run `GAExtractor.exe`.
2. Drag archives (`.rpa`, `.xp3`, `.assets`, `.rgssad`, `.gax`, ...) or a game folder
   into the window, or click "Browse..." / "Folder".
3. **For .gax (CatSystem2)**: specify the path to the game exe in the "EXE (for .gax)" field.
4. Optionally change the output path.
5. Click "Extract".

### CLI usage

```bash
# Extract a single file (format auto-detected)
GAExtractor.exe file.rpa -o output_dir
GAExtractor.exe game.xp3 -o output_dir
GAExtractor.exe Game.rgss3a -o output_dir

# Extract all archives from a folder (auto-detect)
GAExtractor.exe C:\Games\MyGame -o C:\Extracted --auto-detect

# Strict mode (no continue-on-error)
GAExtractor.exe file.rpa -o output --strict

# Disable name sanitization
GAExtractor.exe file.rpa -o output --no-sanitize

# Show version
GAExtractor.exe --version
```

### Running tests

```bash
python run_tests.py
```

### Build from source

```bash
pip install -r requirements.txt
pyinstaller ga_extractor.spec --clean
```

Output: `dist/GAExtractor.exe` (~280 MB, standalone).

---

## CatSystem2 .gax decryption

`.gax` is a proprietary encrypted image format used by CatSystem2 visual novels.
The encryption uses a per-game XOR key that is **hardcoded in the game executable**.

### Supported workflow

1. Find the game exe (e.g. `Game.exe` in the game folder).
2. In GAExtractor GUI: enter the path in the **EXE (for .gax)** field.
3. Click **Extract**. GAExtractor searches for CS2 markers (`.gax`, `.pck`, `.int`,
   `RENDER_TEX`, Japanese strings) and tries to extract a 32-bit key candidate,
   then validates it against actual `.gax` files in the folder.

### Known limitation

CatSystem2 encryption is **per-game**: each game stores its key at a different
hardcoded offset inside the exe. For some games (e.g. *Kabe no Mukou no Tsuma
no Koe 3*, *Wall.exe*) the key offset is not near any CS2 string and cannot be
found generically — it requires manual reverse engineering of the specific exe.

When decryption fails, GAExtractor:

- saves the file as `.bin` (the raw encrypted bytes) for manual analysis;
- shows a popup at the end of extraction summarising how many files were
  decrypted vs. failed, with suggestions for external tools.

### Recommended external tools for unsupported games

If GAExtractor cannot decrypt a particular CS2 game, use one of these
specialised tools (they have per-game key offset databases built-in):

- **[crass](https://github.com/KatyushaScarlet/crass)** — Ciri's CS2/arc
  unpacker, supports many engines including CatSystem2.
- **[arc_conv](http://www.vector.co.jp/soft/dl/win95/art/se475839.html)** —
  Japanese archive converter with CatSystem2 plugin.
- **[Galatea](https://github.com/vn-tools/galatea)** — VN archive extractor.
- **ExtractData** — generic VN asset extractor.
