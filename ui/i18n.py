from typing import Dict, Callable
import locale


TRANSLATIONS: Dict[str, Dict[str, str]] = {
    'ru': {
        'window.title': 'Распаковщик RPA',
        'drop.hint': 'Перетащите .rpa сюда',
        'file.label': 'Файл:',
        'file.browse': 'Обзор...',
        'folder.label': 'Папка назначения:',
        'folder.choose': 'Выбрать...',
        'extract.button': 'Распаковать',
        'cancel.button': 'Отмена',
        'open.folder': 'Открыть папку',
        'progress.status': 'Извлекаю: {0} ({1}/{2})',
        'progress.complete': 'Готово! Извлечено файлов: {0}',
        'progress.file_complete': 'Готово! Извлечено файлов: {0} из {1}',
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
    },
    'en': {
        'window.title': 'RPA Extractor',
        'drop.hint': 'Drop .rpa here',
        'file.label': 'File:',
        'file.browse': 'Browse...',
        'folder.label': 'Destination:',
        'folder.choose': 'Choose...',
        'extract.button': 'Extract',
        'cancel.button': 'Cancel',
        'open.folder': 'Open folder',
        'progress.status': 'Extracting: {0} ({1}/{2})',
        'progress.complete': 'Done! Extracted {0} files.',
        'progress.file_complete': 'Done! Extracted {0} of {1} files.',
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
