# FUTURE PLANS — Feature Backlog

Этот документ фиксирует **изученные** будущие доработки.
**К реализации не приступаем** — только план и оценка.

---

## BUG #1 — XP3 не виден в диалоге и не принимается при drag&drop

**Приоритет:** HIGH
**Сложность:** тривиальная (~5 минут)

### Где
- [ui/main_window.py:542](file:///c:/Projects/rpa-ex/ui/main_window.py#L542) — фильтр `QFileDialog.getOpenFileNames()` не содержит `*.xp3`
- [ui/main_window.py:254](file:///c:/Projects/rpa-ex/ui/main_window.py#L254) — extension check в `dropEvent` не содержит `.xp3`

### Фикс
1. В QFileDialog filter добавить `*.xp3`:
   ```
   'Archive files (*.rpa *.xp3 *.assets *.bundle *.unity3d *.resource *.resS);;'
   'KiriKiri archives (*.xp3);;'
   ```
2. В drop handler расширить проверку расширений:
   ```python
   if pl.endswith('.rpa') or pl.endswith('.xp3') or pl.endswith(('.assets', '.bundle', '.unity3d', '.resS', '.resource')):
   ```
3. Регресс-тест: бросить `.xp3` в окно → должен попасть в список и успешно распаковаться.
4. Добавить unit-тест на `FileSelectionDialog` с .xp3 (если есть).

---

## FEATURE #2 — Интеграция UniExtract2 (https://github.com/bioruebe/uniextract2)

**Приоритет:** MEDIUM (масштабный рефакторинг)
**Объём:** большой

### Что такое UniExtract2
Universal Extractor 2 — AutoIt-обёртка над 50+ внешними extractors (7zip, innoextract, unrar, etc.) для распаковки ЛЮБЫХ архивов: 7z/RAR/ZIP, инсталляторы (Inno, NSIS, MSI), образы дисков (ISO, DMG, VMDK), игровые архивы (Bethesda, Unity, Unreal, KiriKiri, RPG Maker, Visionaire, Ren'Py, Telltale, Wolf, RenPy), мультимедиа, etc.

### Актуальный список поддерживаемых (из FORMATS.md)

**Compressed archives:** 7z, ACE, ALZip, ARC, ARJ, **Asar**, BCM, BGA, bzip2, **Chromium .pak**, CPIO, DGCA, FreeArc, gzip, KGB, deb/rpm, LBR, LZIP, LZH, LZMA, LZO, LZW, LZX, PEA, RAR, StuffIt, TAR, UHARC, UPX, XZ, ZIP, Zoo, ZPAQ

**Installers:** Actual Installer, Advanced Installer, Bitrock, Clickteam, Create Install, Excelsior, Ghost, GOG, Inno Setup, Install4j, InstallAware, Installer VISE, InstallForge, InstallScript, InstallShield, MSCF, Netopsystems FEAD, NSIS, PyInstaller, Self-Extracting Zip, SetupFactory, Smart Install Maker, Spoon, SuperDAT, SymbianOS, Windows Installer, Wise, WiX

**Disk images:** ADF, Android boot, DMG, BIN/CUE, CCD, CSO, DiscJuggler, Dreamcast GDI, ECM, gBurner, IMG, ISO, ISZ, NBH, Nero, PowerISO, MagicISO, MDF/MDS, VDI, VHD, VMDK, WIM

**Multimedia:** animated GIF/PNG, MP3/OGG/FLAC/WMA/M4A → WAV, SWF, FMOD .fsb, sfArk, AVI/MP4/MKV...

**Game archives (у нас уже частично):** Bethesda .bsa/.ba2/.dat, Bruns .um3, Godot .pck, **KiriKiri .xp3 ✅**, LiveMaker, NScripter, Ren'Py **.rpa ✅**, **RPG Maker .rgssad/.rgss2a/.rgss3a/.rpgmvp/.rpgmvo/.rpgmvm** (часть нужно шифровать), Smile Game builder .sgbpack, **Telltale .ttarch**, Unity ✅, Unreal .pak, UTAGE, **Visionaire .vis/.vc001/.vv001**, WinterMute .dcp, **Wolf RPG .wolf**, YU-RIS

**Text-based:** EML, B64/HQX/UU/XX, GNU Gettext, MacBinary, CHM, LIT, HLP, MHT, Outlook DBX, **PHAR**, PDF, Qt .qm, SQLite, **WARC**

**Other:** Enigma Virtual Box, MoleBox, Split files (.001), Thumbs.db cache

### Архитектурное решение

UniExtract2 — AutoIt + внешние бинарники, мы Python. Делать **полный порт 50+ форматов** нерационально. Разумная стратегия: **выборочная интеграция** приоритетных игровых архивов на Python + **опциональный fallback** на 7-Zip CLI для всего остального (как делает UniExtract2 сам).

### Слои архитектуры

#### Слой 1 — расширение `BaseUnpacker` (уже есть)
Каждый формат = отдельный класс в `unpackers/`. Уже:
- `rpa_unpacker.py` — Ren'Py
- `unity_unpacker.py` — Unity (UnityPy)
- `xp3_unpacker.py` — KiriKiri

#### Слой 2 — новые unpacker'ы (по приоритету спроса)

| Формат | Файл | Сложность | Зависимость |
|---|---|---|---|
| RPG Maker MV/MZ/VX/Ace | `rpgm_unpacker.py` | средняя | чистый Python (XOR, header-strip) |
| Wolf RPG Editor .wolf | `wolf_unpacker.py` | средняя | `xdvdfs` или чистый Python |
| Telltale .ttarch | `ttarch_unpacker.py` | средняя | `libttarch` или reverse-engineered pure python |
| Visionaire .vis | `visionaire_unpacker.py` | сложная | reverse-engineering |
| Bethesda .bsa/.ba2 | `bsa_unpacker.py` | средняя | `bsa` (npm-порт на py) |
| Unreal .pak | `pak_unpacker.py` | средняя | `repak` (pip: `repak`) |
| Godot .pck | `godot_pck_unpacker.py` | лёгкая | `gdtoolkit` или pure python |
| StuffIt .sit | `stuffit_unpacker.py` | лёгкая | `unstuff` (CLI) |
| LZH/LHA | `lzh_unpacker.py` | лёгкая | `lhafile` (pip) |
| ALZip .alz | `alz_unpacker.py` | средняя | reverse-engineered |
| StuffIt | sit | лёгкая | unstuffer |

#### Слой 3 — generic 7-Zip wrapper (fallback)

`unpackers/sevenzip_unpacker.py` — обёртка над 7-Zip CLI (или `py7zr` для большинства форматов). Когда ни один специализированный unpacker не справился, **пробуем 7-Zip**. Поддерживает: 7z, RAR5, ZIP, TAR, GZ, BZ2, XZ, ZPAQ, LZH, ACE, ARJ, CPIO, RPM, DEB, ISO, MSI, CAB, WIM, DMG (частично), NSIS (частично).

**Когда применять:** после специализированных unpacker'ов как fallback. Если файл не распознан — пытаемся `7z l` чтобы получить список, и `7z x` для извлечения.

### Детектор форматов
Расширить `core/detector.py`:
```python
class GameFormat(Enum):
    # ... существующие
    RPG_MAKER_RGSSAD = "rpg_maker_rgssad"
    RPG_MAKER_MV = "rpg_maker_mv"
    TELLTALE_TTARCH = "telltale_ttarch"
    WOLF_RPG = "wolf_rpg"
    UNREAL_PAK = "unreal_pak"
    GODOT_PCK = "godot_pck"
    BSA = "bethesda_bsa"
    GENERIC_7ZIP = "generic_7zip"  # fallback
    # ...
```

Детекция по сигнатурам:
- `RGSSAD`: magic `RGSSAD` или `RGSS2A` или `RGSS3A`
- `RPGMVO/MVP/MVM`: XOR-encrypted с 16-байтовым fake header `5250474d56000000 000301 0000000000`
- `TTARCH`: magic `TTarch` (4 байта) + version
- `Wolf`: magic `Wolf RPG` (8 байт) или `WOLF`
- `Unreal PAK`: magic `\x50\x41\x4b\x00` (5-byte versioned header)
- `Godot PCK`: magic `GDPC` (4 байта)
- `BSA`: magic `BSA\x00` или `BTDX`
- `BA2`: magic `BTX2` или `GNRL`

### Этапы реализации

**Этап A — RPG Maker (высокий приоритет, ~2-3 дня):**
1. `unpackers/rpgm_unpacker.py` — поддержка `.rgssad`, `.rgss2a`, `.rgss3a`, `.rpgmvp`, `.rpgmvo`, `.rpgmvm`
2. Детектор: сигнатуры `RGSSAD\0`, `RGSS2A\0`, `RGSS3A\0`, fake-header для MV
3. `core/rpgm_key_extractor.py` — извлечение ключа из System.json / rpg_core.js / XOR-анализ из .rpgmvp
4. Тесты на синтетических + реальных RPG Maker играх

**Этап B — Telltale / Wolf / Unreal / Godot (~3-5 дней):**
1. `unpackers/telltale_unpacker.py` — magic-based header parser
2. `unpackers/wolf_unpacker.py` — index+offset таблица
3. `unpackers/pak_unpacker.py` — UE4 PAK format
4. `unpackers/godot_unpacker.py` — GDPC format

**Этап C — 7-Zip fallback (~1 день):**
1. `unpackers/sevenzip_unpacker.py` — пробует `7z` CLI (если есть в PATH)
2. Если `7z` недоступен — пробует `py7zr` (только .7z)
3. Регистрация как `unpacker = Generic7ZipUnpacker` для unknown форматов

**Этап D — packaging:**
1. В `rpa_extractor.spec` добавить новые unpacker'ы в `hiddenimports`
2. Опционально — бандлить 7z.exe (~1MB) в `bin/7z/`

### Тесты
- Расширить `tests/` под каждый новый формат
- Синтетические файлы (генерируем в helper'ах) + реальные игры пользователя
- Fallback test: неподдерживаемый формат → 7-Zip fallback

### Что НЕ делаем
- Портировать весь AutoIt (~10K строк) — нет смысла
- Поддержку инсталляторов (Inno/NSIS) — слишком узко, оставляем для 7-Zip
- Поддержку мультимедиа-конвертации (mp3→wav и т.п.) — это отдельный use case

---

## FEATURE #3 — RPG-Maker-MV-Decrypter (https://github.com/petschko/rpg-maker-mv-decrypter)

**Приоритет:** MEDIUM
**Объём:** средний (3-5 дней)
**Зависит от:** FEATURE #2 (этап A)

### Что это
Инструмент дешифровки RPG Maker MV/MZ resource-файлов. Шифрование:
- **Images:** `.rpgmvp` / `.png_` — XOR первых N байт с ключом + fake-header 16 байт `RPGMV\0\0\0\0\x00\x03\x01` + padding
- **Audio:** `.rpgmvo` / `.ogg_`, `.rpgmvm` / `.m4a_` — XOR + fake-header
- **Key:** 32 hex символа (16 байт), хранится в `www/js/rpg_core.js` (MV) или `js/rpg_core.js` (MZ)

### Алгоритм (из `Decrypter.js`)

**Default header (16 байт):**
```
Signature: 5250474d56000000 → "RPGMV\0\0\0"
Version:   000301          → 0.3.1
Remain:    0000000000      → padding
```

**Дешифровка файла:**
1. Прочитать 16 байт fake-header
2. Опционально проверить сигнатуру (если `verifyFakeHeader=true`)
3. Удалить 16 байт fake-header
4. XOR первые 16 байт (или `headerLen`) с ключом (разбитым попарно)

**Восстановление PNG без ключа (no-key method):**
1. PNG-файл: `89 50 4E 47 0D 0A 1A 0A 00 00 00 0D 49 48 44 52` (16 байт известного заголовка)
2. Encrypted .rpgmvp: fake_header (16) + encrypted_data (где XOR применён к первым 16 байтам = известному PNG-заголовку)
3. Чтобы восстановить: берём первые 16 байт encrypted = fake_header + XORed_PNG_header
4. Известные XORed_PNG_header[0:16] = `89 50 4E 47 0D 0A 1A 0A 00 00 00 0D 49 48 44 52`
5. Реальный PNG начинается сразу после fake_header (с 32-го байта файла). То есть:
   - `file[32:32+16]` = чистый PNG-header (без XOR!)
   - `file[16:32]` = XORed PNG-header (с fake header)
   - `file[0:16]` = fake_header
6. Значит, **PNG = `file[32:]` + оригинальный PNG header** (восстановленный из `file[16:32]` дексором)
7. **Но на самом деле проще:** Encrypted file = `fake_header (16) + XOR_bytes(16) + raw_data`
   → `decrypted_png = raw_data` начинается с offset 32 и **не зашифрован** дальше (XOR только на первые 16 байт)
   → Восстановление: пропустить 32 байта префикс, добавить правильный PNG-header

### Ключ шифрования — где искать

1. **`System.json`** в `www/data/System.json` (MV) или `data/System.json` (MZ):
   ```json
   { "encryptionKey": "d41d8cd98f00b204e9800998ecf8427e" }
   ```
   Может быть LZ-String сжат.

2. **`rpg_core.js`** в `www/js/rpg_core.js` (MV) или `js/rpg_core.js` (MZ):
   ```js
   Decrypter._encryptionKey = "d41d8cd98f00b204e9800998ecf8427e";
   ```
   Регулярка: `this\._encryptionKey ?= ?"(.*)"`

3. **XOR-анализ из .rpgmvp:**
   Известны первые 16 байт PNG header.
   Encrypted: `fake_header[0:16] + XORed_data[0:16] + raw_data[16:]`
   `key[i] = XORed_data[i] ^ PNG_header[i]` (XOR обратим, XOR(A^K, A) = K)

4. **`readKeyFromGame.js`** — JS-скрипт для встраивания в rpg_core.js для отладки (мы НЕ используем — он запрашивает prompt).

### Формат `.rgssad` / `.rgss2a` / `.rgss3a` (RPG Maker VX Ace / MV-legacy)

**`.rgssad` (RPG Maker XP/VX):**
```
Header: 4 bytes — magic "RGSSAD"
Body: stream of records
  each record: 4 bytes (size) + 4 bytes (key XOR magic) + data
  key rotates after each record
```

**`.rgss2a` (RPG Maker VX):**
```
Header: "RGSS2A" + 4 bytes version
Body: stream of records with key XOR
```

**`.rgss3a` (RPG Maker VX Ace):**
```
Header: "RGSS3A" + 4 bytes version
Body: stream of records with key XOR
```

### Файлы для реализации

```
core/
  rpgm_key_extractor.py    # Извлечение ключа из System.json, rpg_core.js, XOR-анализом
  rpgm_decrypter.py        # XOR-дешифровка + fake-header handling
  rpgm_reader.py           # Парсер .rgssad/.rgss2a/.rgss3a
unpackers/
  rpgm_unpacker.py         # Главный unpacker — сам выбирает стратегию
tests/
  test_rpgm.py             # Тесты: fake-header, XOR, no-key PNG recovery
```

### Этапы реализации

**Этап A (1-2 дня) — MV/MZ decryption:**
1. `core/rpgm_decrypter.py`:
   - Класс `RpgmDecrypter` с параметрами: `key`, `headerLen`, `signature`, `version`, `remain`
   - Методы: `decrypt_file()`, `encrypt_file()`, `restore_png_no_key()`, `verify_header()`
2. `core/rpgm_key_extractor.py`:
   - `extract_from_system_json(path)` — парсит JSON / LZ-String
   - `extract_from_rpg_core_js(path)` — regex + LZ-String fallback
   - `extract_from_rpgmvp(path)` — XOR-анализ известного PNG header
3. `unpackers/rpgm_unpacker.py`:
   - `detect()` — сигнатура fake-header `RPGMV\0\0\0` в первых 8 байт
   - `analyze()` — определяет нужен ли ключ
   - `unpack()`:
     - Шаг 1: ищет System.json / rpg_core.js в папке игры / рядом
     - Шаг 2: если не нашёл — пробует XOR-анализ по первому .rpgmvp
     - Шаг 3: дешифрует все .rpgmvp/.rpgmvo/.rpgmvm в папке
     - Шаг 4: для изображений без ключа применяет `restore_png_no_key()`
4. `core/detector.py`:
   - `GameFormat.RPG_MAKER_MV` = `"rpg_maker_mv"`
   - Детекция по сигнатуре `5250474d56` (RPGMV)
5. `core/extractor.py`: реэкспорт `RpgmUnpacker`

**Этап B (1-2 дня) — RGSSAD:**
1. `core/rpgm_reader.py`:
   - `RgssadReader` — магический, версия, key
   - `Rgss2aReader` — расширенный формат
   - `Rgss3aReader` — формат Ace
2. `unpackers/rgssad_unpacker.py` (или в `rpgm_unpacker.py`):
   - XOR-ключ для каждой записи: `key = (key * 7 + 3) & 0xFFFFFFFF`, XOR с magic
   - Имена файлов: длина + UTF-8 строка
3. Тесты: каждый формат отдельно

**Этап C (1 день) — UI integration:**
1. Drag&drop: расширить extension check на `.rpgmvp/.rpgmvo/.rpgmvm/.rgssad/.rgss2a/.rgss3a`
2. QFileDialog filter: добавить `*.rpgmvp *.rpgmvo *.rpgmvm *.rgssad *.rgss2a *.rgss3a`
3. `_scan_dropped_folder` — искать System.json в подпапках (www/data/, data/)
4. При обнаружении MV-игры: показать в status "Найден RPG Maker MV (ключ: ...)" или "Ключ не найден — будет использован no-key PNG recovery"
5. Опциональный `RPG Maker Key Prompt Dialog` — если ни один метод не сработал

**Этап D (1 день) — тесты:**
1. Синтетические тесты на XOR + fake-header
2. Тест no-key PNG recovery (сравнить с petschko JS)
3. Тест key extraction (с фейковым System.json / rpg_core.js)
4. Тест на реальной RPG Maker MV-игре (если у пользователя есть)

### Лицензия
Petschko's RPG-Maker-MV-Decrypter — MIT. Можем использовать алгоритм, но код пишем свой на Python (не портируем JS).

### Что НЕ делаем
- Не делаем GUI для RPG Maker-специфичных настроек (encryption key input dialog) — сначала auto-detect, ручной input — потом, если попросят
- Не делаем re-encrypt (только decrypt)
- Не поддерживаем RPG Maker MZ отдельно от MV — алгоритм тот же, отличается только путь к System.json
- Не делаем JS-prompt хак (readKeyFromGame.js) — только статический анализ

---

## Общий порядок реализации (когда дадут команду)

1. **BUG #1** — 5 минут → сразу фиксим
2. **FEATURE #2 этап A** (RPG Maker MV/MZ) — 2-3 дня
3. **FEATURE #3 этапы A+B** (RGSSAD + интеграция в MV) — пересекается с #2A
4. **FEATURE #2 этапы B+C** (Telltale/Wolf/Unreal/Godot + 7-Zip fallback) — по запросу

---

## Открытые вопросы (нужно уточнить у пользователя перед реализацией)

1. Какие форматы в приоритете (RPG Maker, Telltale, Wolf, или другие)?
2. Нужен ли 7-Zip fallback (требует 7z.exe или py7zr)?
3. Нужен ли GUI для ручного ввода encryption key (для RPG Maker)?
4. Какие реальные игры у пользователя есть для тестирования (для каждого формата)?
5. Есть ли лицензионные ограничения (например, не использовать `py7zr` из-за GPL)?
