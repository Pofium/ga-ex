# Changelog

## v0.12.13 (2026-08-04) — Godot 4.x PCK v2/v3 fix

### Fixed
- [unpackers/godot_pck_unpacker.py](file:///c:/Projects/rpa-ex/unpackers/godot_pck_unpacker.py):
  полная поддержка формата **PCK v2/v3 (Godot 4.0–4.6+)** — заголовок с
  `file_base`/`dir_offset` и таблицей файлов **в конце архива**, флаги
  `PACK_REL_FILEBASE`/`PACK_DIR_ENCRYPTED`/`PACK_FILE_ENCRYPTED`. Раньше
  понимался только layout Godot 3 (таблица сразу после заголовка), поэтому
  игры на Godot 4.x (напр. *NTR Gambling*, Godot 4.6.3, pack v3) падали с
  «не удалось прочитать записи» — в GUI это выглядело как «Архив повреждён».
  Проверено на реальной игре: 1207 файлов, 0 ошибок.
- Текстуры Godot 4 `.ctex` (GST2): рядом с `.ctex` теперь сохраняется
  читаемая копия изображения (`.webp`/`.png`/`.jpg`), извлечённая из контейнера.
- Пути `res://`, `user://`, `uid://` обрезаются до чистой файловой иерархии.

### Added
- [tests/test_new_formats.py](file:///c:/Projects/rpa-ex/tests/test_new_formats.py):
  регрессионные тесты `TestGodotPckV3` — сборка минимального PCK v3
  (dir_offset в конце), распаковка и `analyze` (версии, file_count).

## v0.12.12 (2026-08-01) — TyranoBuilder asar fix

### Fixed
- [unpackers/asar_unpacker.py](file:///c:/Projects/rpa-ex/unpackers/asar_unpacker.py):
  the asar header parser now supports **two header layouts**. Besides the classic
  asar format (JSON at pickle offset 4), it also handles the TyranoBuilder /
  some Electron builds where the inner pickle carries a second length field
  (`[uint32 json_len][uint32 json_len-4][JSON]`, JSON at offset 8). Previously
  such archives — e.g. *Pervs Hotel* (TyranoScript, ~2847 files) — were detected
  as `UNKNOWN` and could not be extracted. The parser tries length-bounded JSON
  decode at offsets 4 and 8 with a `{`-based fallback, and validates the result.
### Added
- [tests/test_new_formats.py](file:///c:/Projects/rpa-ex/tests/test_new_formats.py):
  3 regression tests — detection and full unpack of the TyranoBuilder asar
  layout (offsets/data verified), plus a standard-asar unpack regression.

## v0.12.11 (2026-07-28) — GS (NW.js) engine support

### Added
- New engine: **GS on NW.js** (e.g. *House of Maids*). Resources are XOR-encrypted
  with a fixed 5-byte key `0A 2B 36 6F 0B` derived from the game's
  `GS.DataPreparer` class. Decrypted output keeps the original directory tree.
- [core/detector.py](file:///c:/Projects/rpa-ex/core/detector.py): new format
  `GS_NWJS`, file detection by content (XOR → known media signature) and folder
  detection by the `GS.DataPreparer`/`needsPreparation` marker in `data/ENGINE.js`
  plus NW.js runtime files. Plain files (e.g. `icon.png`) never false-positive.
- [unpackers/gs_nwjs_unpacker.py](file:///c:/Projects/rpa-ex/unpackers/gs_nwjs_unpacker.py):
  new unpacker — decrypts media (`resources/`) and game scripts (`data/*.json.js`),
  skips engine binaries and plain `data/lib/*.js`. Supports both a whole game
  folder and a single encrypted file.
- [core/extractor.py](file:///c:/Projects/rpa-ex/core/extractor.py),
  [cli.py](file:///c:/Projects/rpa-ex/cli.py),
  [ui/main_window.py](file:///c:/Projects/rpa-ex/ui/main_window.py): wired the new
  unpacker into GUI, CLI and the common pipeline.
- [tests/test_gs_nwjs.py](file:///c:/Projects/rpa-ex/tests/test_gs_nwjs.py): 15
  regression tests (detector for PNG/JPG/OGG/WAV/WOFF/WebM, no-false-positives,
  folder detection, single-file and folder decryption, path-traversal guard).
- [ga_extractor.spec](file:///c:/Projects/rpa-ex/ga_extractor.spec): added
  `unpackers.gs_nwjs_unpacker` to PyInstaller hidden imports.

### How it works
The GS engine wraps NW.js (node-webkit) and encrypts every game resource with a
repeating-XOR cipher. The key is generated at runtime from the seed
`Int32Array([42, 11, 23, 88, 133])` via a WASM function, but it is constant for a
given engine build, so any encrypted media file exposes it through its well-known
header (PNG → `\x89PNG`, JPEG → `\xFF\xD8\xFF`, etc.). GA Extractor derives the key
from content, so it needs no per-game configuration.

## v0.12.10 (2026-07-18) — Unreal AES key UX

### Added
- [ui/main_window.py](file:///c:/Projects/rpa-ex/ui/main_window.py): добавлено постоянное поле `AES (для Unreal .pak)` с сохранением последнего значения, а также popup-запрос ключа только для реально обнаруженных зашифрованных Unreal `.pak`.
- [cli.py](file:///c:/Projects/rpa-ex/cli.py) and [core/base_unpacker.py](file:///c:/Projects/rpa-ex/core/base_unpacker.py): CLI принимает `--aes-key`, а общий pipeline распаковки теперь пробрасывает Unreal AES-ключ во все нужные места.

### Fixed
- [unpackers/pak_unpacker.py](file:///c:/Projects/rpa-ex/unpackers/pak_unpacker.py): добавлены нормализация Unreal AES-ключа, чтение encryption-флага из footer и понятная ошибка для зашифрованного индекса без ключа.
- [ui/i18n.py](file:///c:/Projects/rpa-ex/ui/i18n.py): добавлены локализованные сообщения для AES popup, валидации ключа и предупреждений перед запуском распаковки.
- [tests/test_pak_unpacker.py](file:///c:/Projects/rpa-ex/tests/test_pak_unpacker.py): добавлены регрессии на encrypted Unreal footer и формат AES-ключа.

## v0.12.9 (2026-07-18) — Unreal PAK footer detection hotfix

### Fixed
- [core/detector.py](file:///c:/Projects/rpa-ex/core/detector.py): Unreal `.pak` detection now accepts real UE4/UE5 archives whose magic is stored in the footer, so folder scan no longer misses valid `.pak` files.
- [unpackers/pak_unpacker.py](file:///c:/Projects/rpa-ex/unpackers/pak_unpacker.py): added shared Unreal footer-signature detection and a runtime `pyuepak` Oodle compatibility patch for affected compressed archives.
- [tests/test_detector.py](file:///c:/Projects/rpa-ex/tests/test_detector.py) and [tests/test_pak_unpacker.py](file:///c:/Projects/rpa-ex/tests/test_pak_unpacker.py): added regression tests for footer-based Unreal `.pak` detection.

## v0.12.8 (2026-07-18) — NW.js / self-extracting EXE support

### Added
- [core/detector.py](file:///c:/Projects/rpa-ex/core/detector.py): детект `zipfile`-совместимых `.exe` как `GENERIC_7ZIP` для self-extracting архивов и NW.js-пакетов.

### Fixed
- [core/detector.py](file:///c:/Projects/rpa-ex/core/detector.py): folder scan теперь корректно возвращает итоговый формат `GENERIC_7ZIP`, если в папке найден только встроенный архив в `.exe`.
- [unpackers/sevenzip_unpacker.py](file:///c:/Projects/rpa-ex/unpackers/sevenzip_unpacker.py): распаковка `zipfile`-совместимых `.exe` работает напрямую через стандартную библиотеку Python, без внешнего `7z`.
- [tests/test_detector.py](file:///c:/Projects/rpa-ex/tests/test_detector.py) и [tests/test_new_formats.py](file:///c:/Projects/rpa-ex/tests/test_new_formats.py): добавлены тесты на детект и распаковку self-extracting `.exe`.

## v0.12.7 (2026-07-03) — Fix false Unity detection on MP4

### Fixed
- [core/detector.py](file:///c:/Projects/rpa-ex/core/detector.py): старый Unity bundle heuristic больше не срабатывает на MP4/`ftyp` (раньше Electron-папки ошибочно предлагались как Unity).
- [unpackers/asar_unpacker.py](file:///c:/Projects/rpa-ex/unpackers/asar_unpacker.py): `.asar` распаковка сохраняет подпапки и не “склеивает” пути в один файл.

## v0.12.6 (2026-07-03) — Electron app.asar

### Added
- **Electron app.asar** — полная распаковка `resources\\app.asar` (извлечение файлов по JSON header).

### Changed
- [core/detector.py](file:///c:/Projects/rpa-ex/core/detector.py): добавлен детект `.asar` в file/folder scan.
- [ui/main_window.py](file:///c:/Projects/rpa-ex/ui/main_window.py): `.asar` добавлен в drag&drop и file dialog.

## v0.12.5 (2026-07-03) — UX: Chromium/Electron .pak clarification

### Changed
- [ui/main_window.py](file:///c:/Projects/rpa-ex/ui/main_window.py): если в папке нет поддерживаемых архивов, но есть признаки Electron/Chromium, сообщение объясняет что `*.pak` там не Unreal и подсказывает путь `resources\\app`.

## v0.12.4 (2026-07-03) — Hotfix: Majiro Arc folder scan

### Fixed
- [core/detector.py](file:///c:/Projects/rpa-ex/core/detector.py): folder-scan/drag&drop папки теперь находит **Majiro Arc V3 (.arc)** (раньше .arc добавлялся только при выборе файла).

### Changed
- Убрано упоминание конкретной игры из changelog и текста релиза.

## v0.12.3 (2026-07-02) — Majiro Arc, Telltale, Wolf, Godot PCK

### Added
- **Majiro Arc V3 (.arc)** — полная поддержка (Shift-JIS имена, 12-байтные записи)
  - 360 записей в data1.arc: `.rc8`, `.rct`, медиа-файлы
- **Telltale (.ttarch)** — полная поддержка (T3GZ magic, zlib сжатие)
  - Парсинг object table с детекцией сжатых/несжатых объектов
  - Автоопределение формата по magic bytes (PNG, JPEG, DDS, WAV, OGG)
- **Wolf RPG Editor (.wolf)** — открытие как ZIP + raw WOLF формат
  - Wolf RPG Editor 1.x: ZIP-архив (иногда зашифрован паролем)
  - Wolf RPG Editor 2.x: сырой WOLF binary (детект, TBD)
- **Godot Engine (.pck)** — полная поддержка v0-v2
  - Формат: GDPC magic, uint32/uint64 offsets, MD5 проверка
  - Поддержка embedded PCK в EXE (поиск magic с конца)
  - AES encrypted files (flags=1) — сохраняются с расширением .enc
  - v1: 32-битные оффсеты; v2: 64-битные оффсеты + MD5

### Changed
- [ui/main_window.py](file:///c:/Projects/rpa-ex/ui/main_window.py):
  - Добавлен `MajiroArcUnpacker` в импорты
  - `.arc` добавлен в file dialog filters
  - `.arc` добавлен в авто-детект форматов
- [core/detector.py](file:///c:/Projects/rpa-ex/core/detector.py):
  - `MAJIRO_ARC_MAGIC` в константах
  - Детект Majiro Arc по `MajiroArcV3.000\0` магии
- [core/extractor.py](file:///c:/Projects/rpa-ex/core/extractor.py):
  - `MajiroArcUnpacker` в экспортах
- [README.md](file:///c:/Projects/rpa-ex/README.md):
  - Telltale: `🔍 Детект` → `✅ Полная (T3GZ, zlib)`
  - Wolf RPG: `🔍 Детект` → `✅ ZIP; WOLF raw (частично)`
  - Majiro Arc: `✅ Полная (v3, Shift-JIS)` (новый)
  - Godot PCK: `🔍 Детект` → `✅ Полная (v0-v2, embedded EXE*)`

### Fixed
- [tests/test_new_formats.py](file:///c:/Projects/rpa-ex/tests/test_new_formats.py):
  - Telltale тест: старая магия `TTarch` → правильная магия `T3GZ`
  - Telltale тест: невалидный тест заменён на `test_telltale_unpack_real_header`

### Stats
- 132/132 тестов проходят

## v0.12.2 (2026-06-22) — Fix Qt6WebEngineCore decompression + .pak support

### Fixed
- **EXE не запускался**: `Failed to extract PySide6\Qt6WebEngineCore.dll: decompression resulted in return code 0`
  - Отключён UPX в [ga_extractor.spec](file:///c:/Projects/rpa-ex/ga_extractor.spec)
  - UPX не справлялся со сжатием Qt6WebEngineCore.dll и других больших Qt DLL
  - EXE больше (~280 MB), но запускается надёжно
- **`.pak` не распаковывался**: теперь работает полноценно через [pyuepak](https://pypi.org/project/pyuepak/) (Zlib/Gzip/Oodle/LZ4, AES)

### Added
- **Полная поддержка Unreal Engine .pak v1-v12** через `pyuepak`
- **Zlib / Gzip / Oodle / LZ4** декомпрессия (Oodle через `oo2core_9_win64.dll`)
- **AES-256 шифрование** (требует ключ)
- **6 новых тестов** в `tests/test_pak_unpacker.py`
- `pyuepak>=0.2.8` и `cryptography>=42.0.0` в [requirements.txt](file:///c:/Projects/rpa-ex/requirements.txt)
- `oo2core_9_win64.dll` теперь включён в EXE

### Changed
- [unpackers/pak_unpacker.py](file:///c:/Projects/rpa-ex/unpackers/pak_unpacker.py) — полностью переписан через pyuepak (вместо заглушки)
- [ga_extractor.spec](file:///c:/Projects/rpa-ex/ga_extractor.spec) — добавлены `pyuepak` в datas/binaries/hiddenimports

### Stats
- 132/132 тестов проходят
- EXE: 280 MB (без UPX)

## v0.12.1 (2026-06-21) — Fix UI naming + Unity scene-based organization

### Fixed
- **RU window title** в GUI: было «Распаковщик RPA», стало «GA Extractor — Game Archive Extractor»
- **EN window title** обновлён до «GA Extractor — Game Archive Extractor»
- **Drop hint** теперь перечисляет все поддерживаемые форматы (не только .rpa)
- **`err.invalid.header`** — generic для всех движков (был «Invalid RPA file format»)
- **`.github/workflows/build.yml`** — использовал `rpa_extractor.spec` (несуществующий), теперь `ga_extractor.spec`

### Changed
- **`app.py`** — добавлены `setOrganizationName`, `setApplicationVersion`, `setApplicationDisplayName`
- **Unity output structure** — scene-based organization:
  - `Scenes/<SceneName>/<Type>/<filename>` для ассетов привязанных к сцене
  - `Scenes/_Common/<Type>/<filename>` для ассетов в нескольких сценах
  - `Scenes/_Unreferenced/<Type>/<filename>` для несвязанных
  - Автодетект имён сцен через `globalgamemanagers` → BuildSettings
  - Поддержка обоих форматов BuildSettings: новый `m_Scenes` и старый `scenes`
- **Unity naming** — использует `m_Name` как имя файла (с фильтром MD5-хешей)
- **Empty folders cleanup** — удаляются автоматически после распаковки
  - На Serena Dark Confessions: **6805 пустых папок → 0**

### Added
- **22 теста** для Unity helpers в `tests/test_unity_helpers.py`
- Все 126 тестов проходят

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
