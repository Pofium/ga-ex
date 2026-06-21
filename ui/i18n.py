from typing import Dict, Callable
import locale


TRANSLATIONS: Dict[str, Dict[str, str]] = {
    'ru': {
        'window.title': 'Распаковщик RPA',
        'drop.hint': 'Перетащите .rpa, .assets, .bundle (Unity) или папку с игрой',
        'file.label': 'Файл:',
        'file.browse': 'Обзор...',
        'file.scan_folder': 'Папка',
        'file.scan_folder_tip': 'Выбрать папку с игрой (автодетект .rpa/.assets)',
        'file.clear': 'Очистить',
        'file.clear_tip': 'Очистить список выбранных файлов',
        'folder.label': 'Папка назначения:',
        'folder.choose': 'Выбрать...',
        'folder.scan_path': 'Сканировать',
        'folder.scan_path_tip': 'Сканировать введённый путь (папку или файл)',
        'extract.button': 'Распаковать',
        'cancel.button': 'Отмена',
        'open.folder': 'Открыть папку',
        'progress.status': 'Извлекаю: {0} ({1}/{2})',
        'progress.complete': 'Готово! Извлечено файлов: {0}',
        'progress.file_complete': 'Готово! Извлечено файлов: {0} из {1}',
        'progress.skipped': 'Пропущено файлов: {0}',
        'progress.cancelled': 'Отменено',
        'lang.switch': 'EN',
        'overwrite.title': 'Папка не пуста',
        'overwrite.message': 'Папка уже содержит файлы. Перезаписать?',
        'overwrite.yes': 'Да',
        'overwrite.no': 'Нет',
        'overwrite.subfolder': 'В подпапку',
        'err.invalid.header': 'Неверный формат файла RPA',
        'err.invalid.index': 'Архив поврежден (не удалось прочитать индекс)',
        'err.permission': 'Нет прав на запись в папку',
        'err.disk.space': 'Недостаточно места на диске',
        'err.path.length': 'Путь слишком длинный',
        'err.path.traversal': 'Недопустимый путь в архиве',
        'err.cancelled': 'Распаковка отменена',
        'opt.sanitize': 'Заменять недопустимые символы',
        'opt.long_paths': 'Поддержка длинных путей Windows',
        'opt.continue_on_error': 'Продолжать при ошибках',
        'exe.label': 'EXE (для .gax):',
        'exe.placeholder': 'Опционально: путь к exe игры CatSystem2',
        'exe.choose': 'Обзор...',
        'exe.tip': 'Путь к exe игры CatSystem2 для автоматического извлечения ключа расшифровки .gax',
        'exe.clear': 'Очистить',
        'exe.filter': 'Executable files (*.exe)',
        'gax.hint_title': 'Файлы .gax обнаружены',
        'gax.hint_message': (
            'Обнаружены файлы .gax (CatSystem2).\n\n'
            'Для расшифровки .gax может потребоваться exe игры — '
            'ключ шифрования хранится в нём.\n\n'
            'Укажите путь к exe игры в поле "EXE (для .gax)" ниже.\n'
            'Без exe файлы будут сохранены как .bin (без расшифровки).'
        ),
        'gax.needs_exe_title': 'Для .gax требуется exe',
        'gax.needs_exe_message': (
            'Не удалось расшифровать файлы .gax без exe игры.\n\n'
            'Обработанный файл: {0}\n\n'
            'Укажите путь к exe игры CatSystem2 в поле "EXE (для .gax)" '
            'и повторите распаковку.\n\n'
            'Без exe файлы сохранены как .bin.'
        ),
        'gax.summary_title': 'Итог расшифровки .gax',
        'gax.summary.all_failed': (
            'Не удалось расшифровать ни один из {0} .gax файлов.\n\n'
            'CatSystem2 использует сложное per-game XOR-шифрование. '
            'GAExtractor попробовал 8 стандартных алгоритмов и извлечение '
            'ключа из указанного exe — безуспешно для этой конкретной игры.\n\n'
            'Файлы сохранены как .bin.\n\n'
            'Для полной расшифровки используйте специализированные инструменты:\n'
            '  • crass (https://github.com/KatyushaScarlet/crass)\n'
            '  • arc_conv\n'
            '  • Galatea\n'
            '  • ExtractData'
        ),
        'gax.summary.partial': (
            'Расшифровано {0} из {1} .gax файлов.\n\n'
            'Остальные файлы сохранены как .bin.\n'
            'CatSystem2 использует сложное per-game шифрование — '
            'возможно, для этой игры требуется специализированный инструмент '
            '(crass, arc_conv, Galatea).'
        ),
    },
    'en': {
        'window.title': 'GA Extractor',
        'drop.hint': 'Drop .rpa, .assets, .bundle (Unity) or game folder',
        'file.label': 'File:',
        'file.browse': 'Browse...',
        'file.scan_folder': 'Folder',
        'file.scan_folder_tip': 'Select game folder (auto-detect .rpa/.assets)',
        'file.clear': 'Clear',
        'file.clear_tip': 'Clear selected files list',
        'folder.label': 'Destination:',
        'folder.choose': 'Choose...',
        'folder.scan_path': 'Scan',
        'folder.scan_path_tip': 'Scan the path in the field (folder or file)',
        'extract.button': 'Extract',
        'cancel.button': 'Cancel',
        'open.folder': 'Open folder',
        'progress.status': 'Extracting: {0} ({1}/{2})',
        'progress.complete': 'Done! Extracted {0} files.',
        'progress.file_complete': 'Done! Extracted {0} of {1} files.',
        'progress.skipped': 'Skipped {0} files',
        'progress.cancelled': 'Cancelled',
        'lang.switch': 'RU',
        'overwrite.title': 'Folder not empty',
        'overwrite.message': 'Folder already contains files. Overwrite?',
        'overwrite.yes': 'Yes',
        'overwrite.no': 'No',
        'overwrite.subfolder': 'To subfolder',
        'err.invalid.header': 'Invalid RPA file format',
        'err.invalid.index': 'Archive is corrupted (cannot read index)',
        'err.permission': 'No write permission to folder',
        'err.disk.space': 'Not enough disk space',
        'err.path.length': 'Path too long',
        'err.path.traversal': 'Invalid path in archive',
        'err.cancelled': 'Extraction cancelled',
        'opt.sanitize': 'Sanitize invalid characters',
        'opt.long_paths': 'Windows long path support',
        'opt.continue_on_error': 'Continue on errors',
        'exe.label': 'EXE (for .gax):',
        'exe.placeholder': 'Optional: path to CatSystem2 game exe',
        'exe.choose': 'Browse...',
        'exe.tip': 'Path to CatSystem2 game exe for automatic .gax decryption key extraction',
        'exe.clear': 'Clear',
        'exe.filter': 'Executable files (*.exe)',
        'gax.hint_title': '.gax files detected',
        'gax.hint_message': (
            '.gax files (CatSystem2) detected.\n\n'
            'Decrypting .gax may require the game exe — '
            'the encryption key is embedded in it.\n\n'
            'Specify the path to the game exe in the "EXE (for .gax)" field below.\n'
            'Without the exe, files will be saved as .bin (not decrypted).'
        ),
        'gax.needs_exe_title': 'EXE required for .gax',
        'gax.needs_exe_message': (
            'Could not decrypt .gax files without the game exe.\n\n'
            'Processed file: {0}\n\n'
            'Specify the path to the CatSystem2 game exe in '
            '"EXE (for .gax)" field and retry.\n\n'
            'Without exe, files were saved as .bin.'
        ),
        'gax.summary_title': '.gax decryption summary',
        'gax.summary.all_failed': (
            'Failed to decrypt any of {0} .gax files.\n\n'
            'CatSystem2 uses complex per-game XOR encryption. '
            'GAExtractor tried 8 standard algorithms and key extraction '
            'from the specified exe — unsuccessfully for this particular game.\n\n'
            'Files were saved as .bin.\n\n'
            'For full decryption use specialized tools:\n'
            '  • crass (https://github.com/KatyushaScarlet/crass)\n'
            '  • arc_conv\n'
            '  • Galatea\n'
            '  • ExtractData'
        ),
        'gax.summary.partial': (
            'Decrypted {0} of {1} .gax files.\n\n'
            'The rest are saved as .bin.\n'
            'CatSystem2 uses complex per-game encryption — '
            'this game may require a specialized tool '
            '(crass, arc_conv, Galatea).'
        ),
    },
}


def get_default_lang() -> str:
    sys_locale = locale.getlocale()[0] or ''
    if sys_locale.lower().startswith('ru'):
        return 'ru'
    return 'en'


class I18n:
    def __init__(self, lang: str = None):
        self._lang = lang or get_default_lang()
        self._callbacks: list = []

    @property
    def lang(self) -> str:
        return self._lang

    def set_lang(self, lang: str) -> None:
        if lang in TRANSLATIONS:
            self._lang = lang
            self._notify()

    def t(self, key: str, *args) -> str:
        text = TRANSLATIONS.get(self._lang, {}).get(key, key)
        if args:
            try:
                text = text.format(*args)
            except (IndexError, KeyError):
                pass
        return text

    def on_change(self, callback: Callable[[], None]) -> None:
        self._callbacks.append(callback)

    def _notify(self) -> None:
        for cb in self._callbacks:
            cb()


i18n = I18n()
