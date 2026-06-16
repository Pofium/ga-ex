# Changelog

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
