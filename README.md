# RPA Ex

[🇷🇺 Русский](#русский) | [🇬🇧 English](#english)

---

## Русский

**RPA Ex** — это удобная утилита с графическим интерфейсом для распаковки файлов `.rpa` (архивы ресурсов движка Ren'Py).

### Особенности (v0.8.2)
- **Поддержка Drag&Drop**: Просто перетащите один или несколько файлов `.rpa` в окно программы.
- **Массовая распаковка**: Выделяйте сразу несколько файлов, каждый из них распакуется в свою подпапку.
- **Гибкий выбор пути**: Путь распаковки по умолчанию — папка исходного файла. Вы можете легко изменить его, выбрав другую директорию или просто дописав нужную папку в текстовом поле (папка будет создана автоматически).
- **Поддержка новых форматов**: Распаковывает архивы `RPA-2.0`, `RPA-3.0` и `RPA-3.2`.
- **Защита от уязвимостей**: Защита от извлечения файлов по абсолютным путям или использования `..\` (Path Traversal).
- **Двуязычный интерфейс**: Мгновенное переключение между русским и английским языками.
- **Standalone**: Распространяется как один `.exe` файл, не требует установки Python или других зависимостей.

### Как использовать
1. Скачайте `RPAExtractor-v0.8.2-windows.zip` из релизов и распакуйте его.
2. Запустите `RPAExtractor.exe`.
3. Перетащите `.rpa` файл в окно или нажмите «Обзор...».
4. При необходимости отредактируйте путь распаковки в поле «Папка назначения».
5. Нажмите «Распаковать».

### Сборка из исходников
Требуется Python 3.10+
```bash
pip install -r requirements.txt
pyinstaller rpa_extractor.spec --clean
```

---

## English

**RPA Extractor** is a user-friendly GUI utility for extracting `.rpa` files (Ren'Py engine resource archives).

### Features (v0.8.2)
- **Drag&Drop Support**: Simply drag and drop one or multiple `.rpa` files into the window.
- **Batch Extraction**: Select multiple files at once; each will be extracted into its own subfolder.
- **Flexible Output Path**: The default extraction path is the source file's directory. You can easily change it by selecting another directory or simply typing a new folder name in the text field (the folder will be created automatically).
- **Format Support**: Extracts `RPA-2.0`, `RPA-3.0`, and `RPA-3.2` archives.
- **Security**: Built-in protection against absolute paths and `..\` (Path Traversal) vulnerabilities.
- **Bilingual Interface**: Instant switching between Russian and English.
- **Standalone**: Distributed as a single `.exe` file, requires no Python installation.

### How to use
1. Download `RPAExtractor-v0.8.2-windows.zip` from releases and extract it.
2. Run `RPAExtractor.exe`.
3. Drag & drop an `.rpa` file into the window or click "Browse...".
4. If needed, edit the output path in the "Destination" field.
5. Click "Extract".

### Build from source
Requires Python 3.10+
```bash
pip install -r requirements.txt
pyinstaller rpa_extractor.spec --clean
```