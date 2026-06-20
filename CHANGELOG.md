# Changelog

## v0.12.0 (2026-06-20) — Multi-engine format support

### Added (MAJOR)
- **RPG Maker XP/VX/VX Ace .rgssad/.rgss2a/.rgss3a support**
  - `core/rpgm_reader.py` — `Rgss1aReader`, `Rgss2aReader`, `Rgss3aReader` с rotating key `key = (key * 7 + 3) & 0xFFFFFFFF`
  - `core/rpgm_decrypter.py` — `RpgmDecrypter` для MV/MZ с XOR + fake-header
  - `core/rpgm_decrypter.py` — `find_rpg_maker_key()` извлекает ключ из System.json / rpg_core.js / XOR-анализа PNG
  - `unpackers/rpgm_unpacker.py` — `RpgmUnpacker` с поддержкой всех 4 вариантов RPG Maker
  - `extract_key_from_rpgmvp()` — XOR-анализ первых 16 байт PNG fake-header

- **Telltale .ttarch support** (`unpackers/telltale_unpacker.py`)
  - Magic `TTarch`, детект и заглушка с описанием ограничений

- **Wolf RPG Editor .wolf support** (`unpackers/wolf_unpacker.py`)
  - Детект по расширению и размеру

- **Unreal Engine .pak support** (`unpackers/pak_unpacker.py`)
  - Magic `PAK\0`, детект

- **Godot Engine .pck support** (`unpackers/godot_pck_unpacker.py`)
  - Magic `GDPC` в начале или в конце файла (v3+)
  - Фикс ValueError при чтении через закрытый file handle

- **CatSystem2 .gax support** (`unpackers/gax_unpacker.py`)
  - Magic `\x00\x00\x00\x01`
  - Попытки 8 известных XOR-алгоритмов (xor_size_le, xor_size_rotating,
    xor_pos_byte, xor_pos_byte_rev, xor_magic_rot, xor_size_xor_magic,
    xor_0xff, not_bytes)
  - Автоматический детект формата изображения (PNG/JPG/BMP/GIF/WEBP/MP4)
  - Сохранение расшифрованного в правильном расширении
  - При неудаче — сохранение как .bin с диагностическим warning

- **7-Zip fallback unpacker** (`unpackers/sevenzip_unpacker.py`)
  - Поддержка .7z, .zip, .rar, .tar, .gz, .bz2, .xz, .lzma, .cab, .iso, .msi
  - Авто-поиск 7z.exe в PATH и стандартных путях Windows

- **Расширенный FormatDetector** (`core/detector.py`)
  - 9 новых GameFormat: RPG_MAKER_RGSSAD, RPG_MAKER_RGSS2A, RPG_MAKER_RGSS3A,
    RPG_MAKER_MV, TELLTALE_TTARCH, WOLF_RPG, UNREAL_PAK, GODOT_PCK,
    CATSYSTEM2_GAX, GENERIC_7ZIP
  - Рекурсивный поиск всех новых расширений в `detect_folder()`

- **Bug fix #1**: `ui/main_window.py` — расширены QFileDialog filter и drop
  handler для поддержки всех новых форматов (.xp3, .rgssad, .rgss2a,
  .rgss3a, .rpgmvp, .rpgmvo, .rpgmvm, .wolf, .ttarch, .pak, .pck, .gax)

- **ExtractThread** в `ui/main_window.py` — расширен для всех новых unpacker'ов

### Tests
- 31 новых unit-тестов в `tests/test_new_formats.py`
  - TestRpgmDecrypter, TestRpgmReader, TestRpgmUnpacker
  - TestFormatDetectorExtended, TestStubs
  - TestSevenZipUnpacker, TestGaxDecryption
- Всего 95 тестов, все проходят

### Verified (реальные игры)
- **The Edge Of** (Ren'Py, 494 MB `images.rpa`): 2407 файлов, 0 ошибок
- **Kabe no Mukou no Tsuma no Koe 3** (CatSystem2): 697 файлов `.gax`,
  формат детектируется, попытки расшифровки выполнены,
  данные сохраняются как .bin с предупреждением
  (алгоритм шифрования специфичен для игры, требует ключ из exe)

## v0.11.0 (2026-06-20) — KiriKiri XP3 archive support

### Added (MAJOR)
- **Xp3Reader** (`core/xp3_reader.py`) — парсер формата .xp3 (KiriKiri engine)
  - Поддержка magic `XP3\r\n \n\x1a\x8b\x67\x01`
  - Поддержка цепочки Index Records (бит CONTINUE 0x80 в index_flag)
  - Поддержка zlib-сжатого и raw-индекса
  - Поддержка многосегментных файлов с индивидуальной компрессией
  - Рекурсивный парсинг FILE → sub-chunks (info/segm/adlr/time)
  - UTF-16LE пути файлов
- **Xp3Unpacker** (`unpackers/xp3_unpacker.py`) — наследник BaseUnpacker
  - `name = 'xp3'`, `enable_long_path_support`, `sanitize_filename`, `PathTraversalError`
  - Защита от path traversal
  - Поддержка сжатых и несжатых сегментов
- **GameFormat.KIRIKIRI_XP3** в `core/detector.py`
  - Детекция по magic 11 байт
  - Детекция файлов `.xp3` в папке
- **ExtractThread** в `ui/main_window.py` — авто-выбор Xp3Unpacker по формату

### Tests
- 20 новых unit-тестов в `tests/test_xp3.py` (TestXp3Magic, TestFormatDetector,
  TestXp3Reader, TestXp3Unpacker, TestXp3Integration)
- Все 57 тестов проходят

### Verified
- `Aitsu ni Dakareru Ore no Tsuma` (data.xp3, 796 MB): 1607 файлов, 0 ошибок
  - 844 PNG, 544 OGG, 159 TLG, 28 TJS, 14 MA, 8 ASD, 7 WAV, 1 SLI, 1 MPG, 1 BMP
- `Futei o Uru Tsuma Kawabuchi Hina` (data.xp3, 272 MB): 1532 файла, 0 ошибок
  - 909 PNG, 559 OGG, 28 TJS, 14 MA, 8 ASD, 7 WAV, 6 JPG, 1 MPG
- `Aitsu ni Dakareru Ore no Tsuma` (scenario.xp3, 195 KB): 52 .ks скрипта, 0 ошибок

## v0.10.0 (2026-06-16) — Unity support (UnityPy)

### Added (MAJOR)
- **UnityUnpacker** (`unpackers/unity_unpacker.py`) — full Unity asset extraction via UnityPy
- **Unity asset detection** in `FormatDetector`:
  - `.assets`, `.assets.resS`, `.bundle`, `.unity3d`, `.resS`
  - Extensionless files: `level0`..`levelN`, `globalgamemanagers`, `unity default resources`, `unity_builtin_extra`
  - `resources.assets`, `resources.resource`
- **ExtractThread** auto-selects unpacker by file format (RPA → RpaUnpacker, otherwise → UnityUnpacker)
- Added `UnityPy>=1.25.0` to `requirements.txt`
- **FileSelectionDialog** now shows UnityPy status and warns if not installed
- Optional import: `UnityUnpacker` is `None` if UnityPy is not installed

### Verified
- Tested on real Unity game `Pledge Extra credit` (Unity Mono build):
  - Found 15 Unity assets across all subfolders
  - **Extracted 207 files** (Texture2D, Sprite, AudioClip, Font, etc.)
  - 0 errors, all PNGs are valid

## v0.9.1 (2026-06-15) — Recursive scan, file selection dialog, fixed Open Folder

### Fixed
- **Recursive scan** of folders: searches `.rpa`, `.assets`, `.bundle`, `.unity3d`, `.resS` in **all subfolders**
- **"Open Folder" button** now opens the correct output folder using `os.startfile`
- Improved error message when no archives found

### Added
- **FileSelectionDialog**: after scanning a folder, you can choose which archives to extract
  - Format tag ([RenPy] / [Unity])
  - Sort by folder and name (important for Unity numbered assets)
  - Quick filters: "Select all", "Deselect all", "Only RenPy", "Only Unity"
- `UNITY_ASSET` and `MIXED` formats in `GameFormat` enum
- Detector now also picks up Unity files: `.assets`, `.bundle`, `.unity3d`, `.assets.resS`, `.resS`

## v0.9.0 (2026-06-15) — Architecture refactoring, CLI, tests

### Added
- **Modular architecture**: `core/base_unpacker.py` (ABC), `core/detector.py` (FormatDetector)
- **CLI mode**: `cli.py` — full command-line support with `--auto-detect`, `--strict`, `--no-sanitize`, etc.
- **Folder-based mode in GUI**: new "Folder" button scans a game folder for .rpa files automatically
- **Drag&Drop folder support**: drop a folder onto the window to auto-detect archives
- **37 unit tests** covering sanitization, path traversal, long paths, RPA reader (2.0/3.0)
- New `tests/` directory with `test_sanitize.py`, `test_detector.py`, `test_extractor.py`, `test_rpa_reader.py`
- `run_tests.py` runner

### Fixed (CRITICAL BUG found by tests)
- **Index was not XOR-decoded** in some paths — fixed `RpaReader` to follow reference (rpatool) format

### Changed
- Refactored `extractor.py` → `unpackers/rpa_unpacker.py` (backward-compatible re-export)
- `RpaExtractor` → `RpaUnpacker` (more descriptive name, implements `BaseUnpacker`)
- `extract()` → `unpack()` returning `UnpackResult` dataclass
- `BaseUnpacker` defines the contract for future formats (Unity, etc.)
- Improved `_safe_join` to detect drive letters and reject them

## v0.8.4 (2026-06-05) — Long path support and UX improvements

### Added
- Support for Windows long paths (\\?\ prefix)
- Filename sanitization: replace invalid Windows characters
- Reserved Windows name protection (CON, PRN, AUX, NUL, COMx, LPTx)
- Option to continue extraction when individual files fail
- New UI checkboxes: Sanitize, Long paths, Continue on errors

## v0.8.2 (2026-06-03) — First Public Release

### Added
- Support for RPA-2.0/3.0/3.2 with dynamic XOR key
- GUI on PySide6 with Drag&Drop
- Batch extraction of multiple .rpa files
- Bilingual interface RU/EN with live switching
- Editable output path field
- Auto-update of path on Drag&Drop of new files
- Application icon
- Path traversal protection
- Saving settings via QSettings
- CI workflow for auto-build
