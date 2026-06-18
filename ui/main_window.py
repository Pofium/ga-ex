import os
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QProgressBar, QFileDialog,
    QMessageBox, QComboBox, QApplication, QCheckBox
)
from PySide6.QtCore import QThread, Signal, QSettings, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon

from core.extractor import RpaUnpacker
from core.base_unpacker import UnpackOptions
from core.detector import FormatDetector, GameFormat

from unpackers.unity_unpacker import UnityUnpacker
from unpackers import UNITY_AVAILABLE
from core.errors import RpaError, PathTraversalError, PermissionError
from ui.i18n import i18n


settings = QSettings('RPAExtractor', 'RPAExtractor')


class ExtractThread(QThread):
    progress = Signal(str, int, int)
    file_progress = Signal(str, int, int, int, int)
    finished = Signal(list)
    error = Signal(str)
    current_file = Signal(str)
    skipped = Signal(int)

    def __init__(
        self,
        rpa_files: list,
        output_dir: str,
        sanitize_names: bool = True,
        continue_on_error: bool = True,
        use_long_paths: bool = True,
    ):
        super().__init__()
        self.rpa_files = rpa_files
        self.output_dir = output_dir
        self.sanitize_names = sanitize_names
        self.continue_on_error = continue_on_error
        self.use_long_paths = use_long_paths
        self._extractor: Optional[RpaUnpacker] = None

    def run(self):
        all_extracted = []
        total_files = len(self.rpa_files)
        total_skipped = 0

        detector = FormatDetector()

        for i, rpa_path in enumerate(self.rpa_files):
            if getattr(self, '_cancel_requested', False):
                break

            self.current_file.emit(rpa_path)

            rpa_name = os.path.splitext(os.path.basename(rpa_path))[0]
            file_output_dir = os.path.join(self.output_dir, rpa_name)

            # Защита: если file_output_dir указывает на саму исходную папку
            # (т.е. пытаемся писать рядом с исходным файлом),
            # или папка уже занята файлами игры — создаём уникальную подпапку
            target_dir = os.path.dirname(os.path.abspath(rpa_path))
            if os.path.normcase(file_output_dir) == os.path.normcase(target_dir):
                # Совпадает с исходной папкой — добавляем суффикс
                file_output_dir = file_output_dir + '_unpacked'

            # Создаём подпапку, если не существует
            try:
                os.makedirs(file_output_dir, exist_ok=True)
            except (OSError, PermissionError) as e:
                self.error.emit(f"Cannot create output dir: {e}")
                continue

            try:
                # Автовыбор распаковщика по формату файла
                fmt = detector.detect_file(rpa_path)
                if fmt == GameFormat.RENPY_RPA:
                    unpacker = RpaUnpacker()
                elif fmt == GameFormat.UNKNOWN and UNITY_AVAILABLE:
                    # Пробуем Unity — может это Unity-файл
                    unpacker = UnityUnpacker()
                elif UNITY_AVAILABLE:
                    unpacker = UnityUnpacker()
                else:
                    self.error.emit(f"{os.path.basename(rpa_path)}: unknown format")
                    continue

                options = UnpackOptions(
                    output_dir=file_output_dir,
                    sanitize_names=self.sanitize_names,
                    continue_on_error=self.continue_on_error,
                    use_long_paths=self.use_long_paths,
                )
                self._extractor = unpacker
                result = self._extractor.unpack(
                    rpa_path,
                    options,
                    self._make_progress_callback(i, total_files),
                )
                all_extracted.extend(result.files_extracted)
                if result.skipped:
                    total_skipped += len(result.skipped)
                    self.skipped.emit(total_skipped)
                if result.errors:
                    for err in result.errors:
                        self.error.emit(f"{os.path.basename(rpa_path)}: {err}")
            except RpaError as e:
                self.error.emit(f"{os.path.basename(rpa_path)}: {e}")
            except Exception as e:
                self.error.emit(f"{os.path.basename(rpa_path)}: Unexpected error: {e}")

        self.finished.emit(all_extracted)

    def _make_progress_callback(self, file_index: int, total_files: int):
        def callback(filename: str, current: int, total: int) -> None:
            self.file_progress.emit(filename, current, total, file_index + 1, total_files)
            self.progress.emit(filename, current, total)
        return callback

    def cancel(self) -> None:
        self._cancel_requested = True
        if self._extractor:
            self._extractor.cancel()


class DropZone(QLabel):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._update_text()

    def _update_text(self) -> None:
        self.setText(i18n.t('drop.hint'))
        self.setStyleSheet("""
            QLabel {
                border: 2px dashed #888;
                border-radius: 8px;
                padding: 40px;
                background-color: #f0f0f0;
                color: #666;
                font-size: 14px;
                qproperty-alignment: AlignCenter;
            }
            QLabel:hover {
                border-color: #555;
                background-color: #e8e8e8;
            }
        """)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        """Обрабатывает Drag&Drop — файлы, множество файлов или папку."""
        urls = event.mimeData().urls()
        if not urls:
            return

        # Конвертируем ВСЕ URL в локальные пути
        paths = []
        for url in urls:
            p = url.toLocalFile()
            if p:
                paths.append(p)

        # Логирование drag&drop для отладки
        try:
            import tempfile
            log_path = os.path.join(tempfile.gettempdir(), 'rpa-ex-debug.log')
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(f'\n=== DROP EVENT ===\n')
                f.write(f'URLs: {len(urls)}, paths: {len(paths)}\n')
                for p in paths:
                    f.write(f'  {p} (isfile={os.path.isfile(p) if os.path.exists(p) else "?"}, isdir={os.path.isdir(p) if os.path.exists(p) else "?"})\n')
        except Exception:
            pass

        if not paths:
            return

        # Если бросили папку — сканируем её
        if len(paths) == 1 and os.path.isdir(paths[0]):
            self.parent()._scan_dropped_folder(paths[0])
            return

        # Если бросили несколько файлов или папку с файлами — добавляем то, что можно распаковать
        added = 0
        had_folder = False
        all_assets = []

        for p in paths:
            if os.path.isdir(p):
                had_folder = True
                # Рекурсивно собираем .rpa и .assets из папки
                detector = FormatDetector()
                info = detector.detect_folder(p)
                all_assets.extend(info.assets)
            else:
                all_assets.append(p)

        if had_folder and all_assets:
            # Используем диалог выбора
            from core.detector import AssetInfo
            from ui.file_selection_dialog import FileSelectionDialog

            # Конвертируем в AssetInfo
            detector = FormatDetector()
            asset_infos = []
            for p in all_assets:
                if isinstance(p, str):
                    fmt = detector.detect_file(p)
                    if fmt.value == 'unknown' and p.lower().endswith(('.assets', '.bundle', '.unity3d', '.resS')):
                        from core.detector import GameFormat
                        fmt = GameFormat.UNITY_ASSET
                    try:
                        size = os.path.getsize(p)
                    except OSError:
                        size = 0
                    asset_infos.append(AssetInfo(path=p, size=size, format=fmt))

            dialog = FileSelectionDialog(asset_infos, self.parent())
            if dialog.exec() == FileSelectionDialog.Accepted:
                selected = dialog.get_selected_assets()
                for asset in selected:
                    if asset.path not in self.parent()._rpa_files:
                        self.parent()._rpa_files.append(asset.path)
                        added += 1
        else:
            # Одиночные файлы — добавляем сразу
            for p in all_assets:
                if not os.path.isfile(p):
                    continue
                pl = p.lower()
                if pl.endswith('.rpa') or pl.endswith(('.assets', '.bundle', '.unity3d', '.resS', '.resource')):
                    if p not in self.parent()._rpa_files:
                        self.parent()._rpa_files.append(p)
                        added += 1

        if added > 0:
            self.parent()._update_file_display()
            self.parent()._extract_btn.setEnabled(len(self.parent()._rpa_files) > 0)
            self.parent()._status_label.setText(f'Добавлено файлов: {added}')


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self._rpa_files: list = []
        self._output_dir = ''
        self._extract_thread: Optional[ExtractThread] = None
        self._pending_output_dir = ''
        self._setup_ui()
        self._setup_i18n()
        self._restore_settings()
        # Включаем drag&drop на всё окно (не только на DropZone)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Drag&Drop на всё окно — перенаправляет в DropZone-логику."""
        if event.mimeData().hasUrls():
            self._drop_zone.dropEvent(event)

    def _setup_ui(self) -> None:
        self.setWindowTitle(i18n.t('window.title'))
        self.setMinimumWidth(500)
        
        # Set icon
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            # Also set application icon
            QApplication.instance().setWindowIcon(QIcon(icon_path))

        main_layout = QVBoxLayout(self)

        self._drop_zone = DropZone(self)
        main_layout.addWidget(self._drop_zone)

        file_layout = QHBoxLayout()
        self._file_label = QLabel(i18n.t('file.label'))
        file_layout.addWidget(self._file_label)
        # Clickable button (100% works) — показывает попап со списком файлов
        self._file_edit = QPushButton('(перетащите файлы)')
        self._file_edit.setStyleSheet('QPushButton { text-align: left; padding: 4px 8px; }')
        self._file_edit.setCursor(Qt.PointingHandCursor)
        self._file_edit.clicked.connect(self._on_file_label_clicked)
        file_layout.addWidget(self._file_edit, 1)
        self._file_btn = QPushButton(i18n.t('file.browse'))
        self._file_btn.clicked.connect(self._browse_rpa)
        file_layout.addWidget(self._file_btn)
        self._folder_scan_btn = QPushButton(i18n.t('file.scan_folder'))
        self._folder_scan_btn.setToolTip(i18n.t('file.scan_folder_tip'))
        self._folder_scan_btn.clicked.connect(self._browse_game_folder)
        file_layout.addWidget(self._folder_scan_btn)
        self._clear_files_btn = QPushButton(i18n.t('file.clear'))
        self._clear_files_btn.setToolTip(i18n.t('file.clear_tip'))
        self._clear_files_btn.clicked.connect(self._clear_files)
        file_layout.addWidget(self._clear_files_btn)
        main_layout.addLayout(file_layout)

        folder_layout = QHBoxLayout()
        self._folder_label = QLabel(i18n.t('folder.label'))
        folder_layout.addWidget(self._folder_label)
        self._folder_edit = QLineEdit()
        self._folder_edit.textChanged.connect(self._on_folder_changed)
        folder_layout.addWidget(self._folder_edit)
        self._folder_btn = QPushButton(i18n.t('folder.choose'))
        self._folder_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(self._folder_btn)
        self._scan_path_btn = QPushButton(i18n.t('folder.scan_path'))
        self._scan_path_btn.setToolTip(i18n.t('folder.scan_path_tip'))
        self._scan_path_btn.clicked.connect(self._scan_path_from_input)
        folder_layout.addWidget(self._scan_path_btn)
        main_layout.addLayout(folder_layout)

        lang_layout = QHBoxLayout()
        lang_layout.addStretch()
        self._lang_combo = QComboBox()
        self._lang_combo.addItems(['RU', 'EN'])
        self._lang_combo.currentTextChanged.connect(self._change_lang)
        lang_layout.addWidget(QLabel('Language:'))
        lang_layout.addWidget(self._lang_combo)
        main_layout.addLayout(lang_layout)

        options_layout = QHBoxLayout()
        self._sanitize_chk = QCheckBox(i18n.t('opt.sanitize'))
        self._sanitize_chk.setChecked(True)
        options_layout.addWidget(self._sanitize_chk)
        self._long_paths_chk = QCheckBox(i18n.t('opt.long_paths'))
        self._long_paths_chk.setChecked(True)
        options_layout.addWidget(self._long_paths_chk)
        self._continue_chk = QCheckBox(i18n.t('opt.continue_on_error'))
        self._continue_chk.setChecked(True)
        options_layout.addWidget(self._continue_chk)
        options_layout.addStretch()
        main_layout.addLayout(options_layout)

        self._extract_btn = QPushButton(i18n.t('extract.button'))
        self._extract_btn.clicked.connect(self._start_extract)
        self._extract_btn.setEnabled(False)
        main_layout.addWidget(self._extract_btn)

        self._cancel_btn = QPushButton(i18n.t('cancel.button'))
        self._cancel_btn.clicked.connect(self._cancel_extract)
        self._cancel_btn.setVisible(False)
        main_layout.addWidget(self._cancel_btn)

        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        main_layout.addWidget(self._progress_bar)

        self._status_label = QLabel('')
        main_layout.addWidget(self._status_label)

        self._open_folder_btn = QPushButton(i18n.t('open.folder'))
        self._open_folder_btn.clicked.connect(self._open_output_folder)
        self._open_folder_btn.setVisible(False)
        main_layout.addWidget(self._open_folder_btn)

    def _setup_i18n(self) -> None:
        def update_ui() -> None:
            self.setWindowTitle(i18n.t('window.title'))
            self._drop_zone._update_text()
            self._file_label.setText(i18n.t('file.label'))
            self._file_btn.setText(i18n.t('file.browse'))
            self._folder_scan_btn.setText(i18n.t('file.scan_folder'))
            self._folder_scan_btn.setToolTip(i18n.t('file.scan_folder_tip'))
            self._clear_files_btn.setText(i18n.t('file.clear'))
            self._clear_files_btn.setToolTip(i18n.t('file.clear_tip'))
            self._folder_label.setText(i18n.t('folder.label'))
            self._folder_btn.setText(i18n.t('folder.choose'))
            self._scan_path_btn.setText(i18n.t('folder.scan_path'))
            self._scan_path_btn.setToolTip(i18n.t('folder.scan_path_tip'))
            self._extract_btn.setText(i18n.t('extract.button'))
            self._cancel_btn.setText(i18n.t('cancel.button'))
            self._open_folder_btn.setText(i18n.t('open.folder'))
            self._sanitize_chk.setText(i18n.t('opt.sanitize'))
            self._long_paths_chk.setText(i18n.t('opt.long_paths'))
            self._continue_chk.setText(i18n.t('opt.continue_on_error'))

        i18n.on_change(update_ui)

    def _restore_settings(self) -> None:
        last_lang = settings.value('language', '')
        if last_lang:
            i18n.set_lang(last_lang.lower())
            idx = 0 if last_lang.lower() == 'ru' else 1
            self._lang_combo.setCurrentIndex(idx)

        last_folder = settings.value('lastFolder', '')
        if last_folder and os.path.exists(last_folder):
            self._output_dir = last_folder
            self._folder_edit.setText(last_folder)

    def set_rpa_file(self, filepath: str) -> None:
        if filepath not in self._rpa_files:
            self._rpa_files.append(filepath)
        self._update_file_display()
        if len(self._rpa_files) == 1:
            self._output_dir = os.path.dirname(filepath)
        else:
            common = os.path.commonpath(self._rpa_files)
            self._output_dir = common
        self._folder_edit.setText(self._output_dir)
        self._extract_btn.setEnabled(len(self._rpa_files) > 0)
        settings.setValue('lastFile', filepath)

    def _on_folder_changed(self, text: str) -> None:
        self._output_dir = text

    def _on_file_label_clicked(self, _event) -> None:
        """Клик на метку 'X files selected' — показывает попап с галочками."""
        if not self._rpa_files:
            QMessageBox.information(
                self,
                'No files',
                'Нет выбранных файлов.\n'
                'Перетащите файлы или папку с игрой в окно.'
            )
            return

        from ui.file_selection_dialog import FileSelectionDialog
        from core.detector import AssetInfo, GameFormat, FormatDetector

        # Конвертируем self._rpa_files в AssetInfo
        detector = FormatDetector()
        asset_infos = []
        for p in self._rpa_files:
            try:
                size = os.path.getsize(p)
            except OSError:
                size = 0
            fmt = detector.detect_file(p)
            if fmt.value == 'unknown' and p.lower().endswith(('.assets', '.bundle', '.unity3d', '.resS', '.resource')):
                fmt = GameFormat.UNITY_ASSET
            asset_infos.append(AssetInfo(path=p, size=size, format=fmt))

        dialog = FileSelectionDialog(asset_infos, self)
        if dialog.exec() == FileSelectionDialog.Accepted:
            selected = dialog.get_selected_assets()
            self._rpa_files = [a.path for a in selected]
            self._update_file_display()
            self._extract_btn.setEnabled(len(self._rpa_files) > 0)
            self._status_label.setText(f'Выбрано: {len(self._rpa_files)} файлов')

    def _update_file_display(self) -> None:
        if len(self._rpa_files) == 0:
            self._file_edit.setText('')
        elif len(self._rpa_files) == 1:
            self._file_edit.setText(self._rpa_files[0])
        else:
            self._file_edit.setText(f'{len(self._rpa_files)} files selected')

    def _browse_rpa(self) -> None:
        start_dir = ''
        if self._rpa_files:
            start_dir = os.path.dirname(self._rpa_files[0])
        filepaths, _ = QFileDialog.getOpenFileNames(
            self,
            'Select archive files (.rpa, .assets, .bundle, .unity3d, .resource)',
            start_dir,
            'Archive files (*.rpa *.assets *.bundle *.unity3d *.resource *.resS);;'
            'RenPy archives (*.rpa);;'
            'Unity assets (*.assets *.bundle *.unity3d);;'
            'All files (*.*)'
        )
        for filepath in filepaths:
            if filepath and filepath not in self._rpa_files:
                self._rpa_files.append(filepath)
        if filepaths:
            self._update_file_display()
            if len(self._rpa_files) == 1:
                self._output_dir = os.path.dirname(self._rpa_files[0])
            else:
                self._output_dir = os.path.commonpath(self._rpa_files)
            self._folder_edit.setText(self._output_dir)
        self._extract_btn.setEnabled(len(self._rpa_files) > 0)

    def _browse_folder(self) -> None:
        start_dir = self._output_dir if self._output_dir else ''
        folder = QFileDialog.getExistingDirectory(
            self,
            'Select output folder',
            start_dir
        )
        if folder:
            self._output_dir = folder
            self._folder_edit.setText(folder)
            settings.setValue('lastFolder', folder)

    def _browse_game_folder(self) -> None:
        """Выбор папки с игрой → автодетект .rpa файлов."""
        start_dir = self._output_dir if self._output_dir else ''
        folder = QFileDialog.getExistingDirectory(
            self,
            'Select game folder',
            start_dir
        )
        if not folder:
            return
        self._scan_dropped_folder(folder)

    def _clear_files(self) -> None:
        """Очищает список выбранных файлов."""
        if not self._rpa_files:
            return
        reply = QMessageBox.question(
            self,
            'Clear files',
            f'Удалить все {len(self._rpa_files)} выбранных файлов из списка?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._rpa_files.clear()
            self._update_file_display()
            self._extract_btn.setEnabled(False)
            self._status_label.setText('Список очищен')

    def _scan_path_from_input(self) -> None:
        """Сканирует папку, путь которой введён в поле."""
        path = self._folder_edit.text().strip()
        if not path:
            QMessageBox.warning(self, 'Empty path', 'Введите путь к папке с игрой')
            return
        # Убираем кавычки если есть (когда пользователь копирует путь с пробелами)
        path = path.strip('"').strip("'")
        if not os.path.exists(path):
            QMessageBox.critical(
                self, 'Path not found',
                f'Путь не существует:\n{path}'
            )
            return
        if os.path.isfile(path):
            # Если это файл — добавляем напрямую
            self.set_rpa_file(path)
            return
        # Это папка — сканируем
        self._scan_dropped_folder(path)

    def _scan_dropped_folder(self, folder: str) -> None:
        """Обработка папки с игрой: рекурсивный поиск .rpa / .assets с диалогом выбора."""
        from core.detector import FormatDetector
        detector = FormatDetector()
        try:
            info = detector.detect_folder(folder)
        except Exception as e:
            QMessageBox.critical(
                self,
                'Detection error',
                f'Ошибка при сканировании:\n{folder}\n\n{e}'
            )
            return

        # Отладка: пишем в лог-файл
        try:
            import tempfile
            log_path = os.path.join(tempfile.gettempdir(), 'rpa-ex-debug.log')
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(f'\n--- {folder} ---\n')
                f.write(f'Format: {info.format}\n')
                f.write(f'Found {len(info.assets)} assets\n')
                for a in info.assets:
                    f.write(f'  [{a.format.value}] {a.path}\n')
        except Exception:
            pass

        if not info.assets:
            # Соберём что ЕСТЬ в папке для отладки
            try:
                items = os.listdir(folder)[:30]
            except Exception as e:
                items = [f'ERROR: {e}']
            QMessageBox.information(
                self,
                'No archives found',
                f'Не найдено архивов в:\n{folder}\n\n'
                f'Рекурсивный поиск выполнен.\n'
                f'Первые файлы в папке:\n' + '\n'.join(items[:15])
            )
            return

        # Показываем диалог выбора файлов
        from ui.file_selection_dialog import FileSelectionDialog
        dialog = FileSelectionDialog(info.assets, self)
        if dialog.exec() != FileSelectionDialog.Accepted:
            return

        selected_assets = dialog.get_selected_assets()
        if not selected_assets:
            return

        # Добавляем выбранные файлы
        for asset in selected_assets:
            if asset.path not in self._rpa_files:
                self._rpa_files.append(asset.path)

        self._update_file_display()

        # Определяем правильную output_dir:
        # ВСЕГДА создаём новую подпапку, чтобы НИКОГДА не писать в исходную папку игры
        folder_abs = os.path.abspath(folder)
        parent_dir = os.path.dirname(folder_abs)
        folder_name = os.path.basename(folder_abs)

        # Если folder — это *_Data подпапка Unity, выход — в корень игры + _extracted
        # Иначе — в родительскую папку + <имя_игры>_extracted
        if folder_name.endswith('_Data'):
            game_root = parent_dir
        else:
            game_root = folder

        # Берём имя игры — это либо родительский каталог *_Data, либо сам folder
        game_name = os.path.basename(os.path.abspath(game_root))
        # Очищаем имя от запрещённых символов
        safe_game_name = ''.join(c if c.isalnum() or c in ' ._-' else '_' for c in game_name)
        new_output = os.path.join(parent_dir, f'{safe_game_name}_extracted')

        # Всегда перезаписываем output_dir на безопасный
        self._output_dir = new_output

        # Гарантируем что output_dir существует
        try:
            os.makedirs(self._output_dir, exist_ok=True)
        except Exception as e:
            QMessageBox.warning(
                self,
                'Cannot create output',
                f'Не удалось создать папку для распаковки:\n{self._output_dir}\n\n{e}'
            )
            return

        self._folder_edit.setText(self._output_dir)

        self._extract_btn.setEnabled(len(self._rpa_files) > 0)
        self._status_label.setText(
            f'Готово: выбрано {len(selected_assets)} из {len(info.assets)} архивов'
        )

    def _change_lang(self, lang: str) -> None:
        i18n.set_lang(lang.lower())
        settings.setValue('language', lang.lower())

    def _start_extract(self) -> None:
        if not self._rpa_files or not all(os.path.exists(f) for f in self._rpa_files):
            QMessageBox.warning(self, 'Error', i18n.t('err.invalid.header'))
            return

        output_dir = self._output_dir

        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        self._extract_btn.setVisible(False)
        self._cancel_btn.setVisible(True)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._status_label.setText(i18n.t('progress.status', '', 0, len(self._rpa_files)))

        self._extract_thread = ExtractThread(
            self._rpa_files,
            output_dir,
            sanitize_names=self._sanitize_chk.isChecked(),
            continue_on_error=self._continue_chk.isChecked(),
            use_long_paths=self._long_paths_chk.isChecked(),
        )
        self._extract_thread.progress.connect(self._on_progress)
        self._extract_thread.file_progress.connect(self._on_file_progress)
        self._extract_thread.current_file.connect(self._on_current_file)
        self._extract_thread.skipped.connect(self._on_skipped)
        self._extract_thread.finished.connect(self._on_finished)
        self._extract_thread.error.connect(self._on_error)
        self._extract_thread.start()

    def _cancel_extract(self) -> None:
        if self._extract_thread:
            self._extract_thread.cancel()
            self._extract_thread.wait()
        self._on_cancelled()

    def _on_progress(self, filename: str, current: int, total: int) -> None:
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self._status_label.setText(i18n.t('progress.status', filename, current, total))

    def _on_file_progress(self, filename: str, current: int, total: int, file_num: int, total_files: int) -> None:
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self._status_label.setText(f'[{file_num}/{total_files}] {i18n.t("progress.status", filename, current, total)}')

    def _on_current_file(self, filepath: str) -> None:
        basename = os.path.basename(filepath)
        self._status_label.setText(f'Processing: {basename}...')

    def _on_skipped(self, count: int) -> None:
        self._status_label.setText(i18n.t('progress.skipped', count))

    def _on_finished(self, files: list) -> None:
        self._extract_btn.setVisible(True)
        self._extract_btn.setEnabled(True)
        self._cancel_btn.setVisible(False)
        self._status_label.setText(i18n.t('progress.complete', len(files)))
        self._open_folder_btn.setVisible(True)
        # Сохраняем в нормализованном виде — пользователь увидит ЭТУ папку
        self._pending_output_dir = os.path.normpath(self._output_dir)

    def _on_error(self, message: str) -> None:
        self._extract_btn.setVisible(True)
        self._extract_btn.setEnabled(True)
        self._cancel_btn.setVisible(False)

        err_key = 'err.invalid.index'
        if 'permission' in message.lower():
            err_key = 'err.permission'
        elif 'space' in message.lower():
            err_key = 'err.disk.space'
        elif 'path' in message.lower() or 'traversal' in message.lower():
            err_key = 'err.path.traversal'
        elif 'header' in message.lower() or 'format' in message.lower():
            err_key = 'err.invalid.header'

        QMessageBox.critical(self, 'Error', i18n.t(err_key))
        self._progress_bar.setVisible(False)

    def _on_cancelled(self) -> None:
        self._extract_btn.setVisible(True)
        self._extract_btn.setEnabled(True)
        self._cancel_btn.setVisible(False)
        self._progress_bar.setVisible(False)
        self._status_label.setText(i18n.t('progress.cancelled'))

    def _open_output_folder(self) -> None:
        """Открывает папку с распакованными файлами в проводнике Windows."""
        if not self._pending_output_dir:
            return

        # Нормализуем путь для Windows
        target = os.path.normpath(self._pending_output_dir)
        if not os.path.exists(target):
            QMessageBox.warning(
                self,
                'Folder not found',
                f'Output folder no longer exists:\n{target}'
            )
            return

        # На Windows os.startfile — самый надёжный способ открыть проводник
        try:
            if sys.platform == 'win32':
                os.startfile(target)  # открывает в Explorer
            elif sys.platform == 'darwin':
                subprocess.run(['open', target])
            else:
                subprocess.run(['xdg-open', target])
        except Exception as e:
            QMessageBox.critical(
                self,
                'Cannot open folder',
                f'Failed to open:\n{target}\n\nError: {e}'
            )
