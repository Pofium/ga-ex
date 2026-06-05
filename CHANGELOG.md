## v0.8.4 (2026-06-05) — Long path support and UX improvements

### Added
- Support for Windows long paths (\\?\ prefix) — fixes "Path too long" error
- Filename sanitization: replace invalid Windows characters (<>:"/\\|?*)
- Reserved Windows name protection (CON, PRN, AUX, NUL, COMx, LPTx)
- Option to continue extraction when individual files fail
- Skipped files are logged and shown in status bar
- Browse button opens dialog in the folder of the selected .rpa file
- Browse folder starts from the current output path
- Common parent folder is used for output when extracting multiple files
- New UI options (checkboxes): Sanitize, Long paths, Continue on errors

### Changed
- Browse and Folder buttons now remember last used paths

## v0.8.2 (2026-06-03) — First Public Release

### Added
- Support for RPA-2.0/3.0/3.2 with dynamic XOR key
- GUI on PySide6 with Drag&Drop
- Batch extraction of multiple .rpa files
- Bilingual interface RU/EN with live switching
- Editable output path field (new subfolders are created automatically)
- Auto-update of path on Drag&Drop of new files
- Application icon
- Path traversal protection
- Saving settings via QSettings
- CI workflow for auto-build
