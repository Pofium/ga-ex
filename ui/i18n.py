from typing import Dict, Callable
import locale


TRANSLATIONS: Dict[str, Dict[str, str]] = {
    'ru': {
        'window.title': 'GA Extractor — Game Archive Extractor',
        'drop.hint': (
            'Перетащите .rpa, .xp3, .rgss3a, .assets, .bundle, '
            '.gax, .pck, .wolf, .ttarch и др. или папку с игрой'
        ),
        'file.label': 'Файл:',
        'file.browse': 'Обзор...',
        'file.scan_folder': 'Папка',
        'file.scan_folder_tip': (
            'Выбрать папку с игрой (автодетект архивов всех поддерживаемых движков)'
        ),
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
        'err.invalid.header': 'Неверный формат файла или архив повреждён',
        'err.invalid.index': 'Архив поврежден (не удалось прочитать индекс)',
        'err.permission': 'Нет прав на запись в папку',
        'err.disk.space': 'Недостаточно места на диске',
        'err.path.length': 'Путь слишком длинный',
        'err.path.traversal': 'Недопустимый путь в архиве',
        'err.unreal.aes_required': 'Для этого Unreal .pak требуется AES-ключ',
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
        'unreal.aes.label': 'AES (для Unreal .pak):',
        'unreal.aes.placeholder': 'Опционально: AES-ключ Unreal .pak (hex, 64 символа)',
        'unreal.aes.tip': 'AES-ключ для зашифрованных Unreal Engine .pak архивов',
        'unreal.aes.clear': 'Очистить',
        'unreal.aes.prompt_title': 'Обнаружен зашифрованный Unreal .pak',
        'unreal.aes.prompt_message': (
            'Обнаружено {0} зашифрованных Unreal .pak файлов.\n\n'
            'Вставьте AES-ключ, чтобы распаковать их напрямую.\n\n'
            'Файлы:\n{1}\n\n'
            '{2}'
            'Ожидается hex-ключ длиной 64 символа (32 байта).\n'
            'Пример: 0xAABBCC...'
        ),
        'unreal.aes.guid_hint': 'Encryption GUID: {0}\nЭто не сам AES-ключ, а идентификатор.\n\n',
        'unreal.aes.invalid_title': 'Неверный AES-ключ Unreal',
        'unreal.aes.invalid_message': (
            'Не удалось принять AES-ключ.\n\n{0}\n\n'
            'Ожидается hex-строка длиной 64 символа (32 байта), '
            'с префиксом 0x или без него.'
        ),
        'unreal.aes.required_title': 'Нужен AES-ключ Unreal',
        'unreal.aes.required_message': (
            'Среди выбранных файлов есть зашифрованный Unreal .pak.\n\n'
            'Без AES-ключа его индекс не читается, поэтому распаковка не начата.\n\n'
            'Укажите ключ в поле "AES (для Unreal .pak)" или вставьте его в popup.'
        ),
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
        'window.title': 'GA Extractor — Game Archive Extractor',
        'drop.hint': (
            'Drop .rpa, .xp3, .rgss3a, .assets, .bundle, '
            '.gax, .pck, .wolf, .ttarch, etc. or game folder'
        ),
        'file.label': 'File:',
        'file.browse': 'Browse...',
        'file.scan_folder': 'Folder',
        'file.scan_folder_tip': (
            'Select game folder (auto-detect archives of all supported engines)'
        ),
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
        'err.invalid.header': 'Invalid file format or corrupted archive',
        'err.invalid.index': 'Archive is corrupted (cannot read index)',
        'err.permission': 'No write permission to folder',
        'err.disk.space': 'Not enough disk space',
        'err.path.length': 'Path too long',
        'err.path.traversal': 'Invalid path in archive',
        'err.unreal.aes_required': 'This Unreal .pak requires an AES key',
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
        'unreal.aes.label': 'AES (for Unreal .pak):',
        'unreal.aes.placeholder': 'Optional: Unreal .pak AES key (hex, 64 chars)',
        'unreal.aes.tip': 'AES key for encrypted Unreal Engine .pak archives',
        'unreal.aes.clear': 'Clear',
        'unreal.aes.prompt_title': 'Encrypted Unreal .pak detected',
        'unreal.aes.prompt_message': (
            'Detected {0} encrypted Unreal .pak files.\n\n'
            'Paste the AES key to extract them directly.\n\n'
            'Files:\n{1}\n\n'
            '{2}'
            'Expected value: 64 hex characters (32 bytes).\n'
            'Example: 0xAABBCC...'
        ),
        'unreal.aes.guid_hint': 'Encryption GUID: {0}\nThis is not the AES key itself.\n\n',
        'unreal.aes.invalid_title': 'Invalid Unreal AES key',
        'unreal.aes.invalid_message': (
            'Could not accept the AES key.\n\n{0}\n\n'
            'Expected a 64-character hex string (32 bytes), '
            'with or without the 0x prefix.'
        ),
        'unreal.aes.required_title': 'Unreal AES key required',
        'unreal.aes.required_message': (
            'The selected files include an encrypted Unreal .pak.\n\n'
            'Without the AES key its index cannot be read, so extraction was not started.\n\n'
            'Enter the key in the "AES (for Unreal .pak)" field or paste it in the popup.'
        ),
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
