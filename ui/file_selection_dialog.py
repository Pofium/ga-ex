"""Диалог выбора файлов для распаковки с превью."""
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QCheckBox,
    QDialogButtonBox, QFileDialog
)
from PySide6.QtCore import Qt


class FileSelectionDialog(QDialog):
    """Диалог выбора файлов для распаковки.

    Позволяет выбрать какие из найденных архивов распаковывать.
    Сортирует по наименованию папок (для Unity это важно — order matters).
    """

    def __init__(self, assets, parent=None):
        """assets: List[AssetInfo] из FormatDetector.detect_folder()."""
        super().__init__(parent)
        self.setWindowTitle('Выбрать файлы для распаковки')
        self.setMinimumSize(600, 400)

        # Сортируем: сначала по типу, потом по размеру папки (Unity нумерованные ресурсы)
        self._assets = sorted(assets, key=lambda a: (
            0 if a.format.value == 'renpy_rpa' else 1,  # сначала Ren'Py
            os.path.dirname(a.path).lower(),  # потом по папке
            os.path.basename(a.path).lower(),  # потом по имени
        ))

        layout = QVBoxLayout(self)

        # Header
        total_size = sum(a.size for a in assets)
        size_mb = total_size / (1024 * 1024)
        has_rpa = any(a.format.value == 'renpy_rpa' for a in assets)
        has_unity = any(a.format.value == 'unity_asset' for a in assets)

        msg = f'Найдено {len(assets)} архив(ов) ({size_mb:.1f} MB)\nВыберите какие распаковать:'
        if has_unity:
            try:
                import UnityPy  # noqa
                msg += '\n\nUnity assets: распаковка поддерживается (UnityPy установлен).'
            except ImportError:
                msg += '\n\n⚠ Unity assets найдены, но UnityPy не установлен.\nУстановите: pip install UnityPy'

        layout.addWidget(QLabel(msg))

        # Top buttons
        top_buttons = QHBoxLayout()
        self._select_all_btn = QPushButton('Выбрать все')
        self._select_all_btn.clicked.connect(self._select_all)
        self._deselect_all_btn = QPushButton('Снять все')
        self._deselect_all_btn.clicked.connect(self._deselect_all)
        self._select_rpa_btn = QPushButton('Только RenPy .rpa')
        self._select_rpa_btn.clicked.connect(self._select_only_rpa)
        self._select_unity_btn = QPushButton('Только Unity')
        self._select_unity_btn.clicked.connect(self._select_only_unity)
        top_buttons.addWidget(self._select_all_btn)
        top_buttons.addWidget(self._deselect_all_btn)
        top_buttons.addWidget(self._select_rpa_btn)
        top_buttons.addWidget(self._select_unity_btn)
        top_buttons.addStretch()
        layout.addLayout(top_buttons)

        # Список файлов
        self._list = QListWidget()
        for asset in self._assets:
            item = QListWidgetItem(self._format_item(asset))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, asset)
            self._list.addItem(item)
        self._list.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._list)

        # Bottom buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Распаковать выбранные')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _format_item(self, asset) -> str:
        """Форматирует строку для отображения в списке."""
        size_mb = asset.size / (1024 * 1024)
        fmt_tag = '[RenPy]' if asset.format.value == 'renpy_rpa' else '[Unity]'
        rel = os.path.basename(os.path.dirname(asset.path)) or '/'
        return f'{fmt_tag} {rel}/{os.path.basename(asset.path)} ({size_mb:.1f} MB)'

    def _on_item_changed(self, _item):
        # Счётчик меняется в _update_count_label если понадобится
        pass

    def _select_all(self):
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.Checked)

    def _deselect_all(self):
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.Unchecked)

    def _select_only_rpa(self):
        for i in range(self._list.count()):
            item = self._list.item(i)
            asset = item.data(Qt.UserRole)
            item.setCheckState(
                Qt.Checked if asset.format.value == 'renpy_rpa' else Qt.Unchecked
            )

    def _select_only_unity(self):
        for i in range(self._list.count()):
            item = self._list.item(i)
            asset = item.data(Qt.UserRole)
            item.setCheckState(
                Qt.Checked if asset.format.value == 'unity_asset' else Qt.Unchecked
            )

    def get_selected_assets(self):
        """Возвращает список выбранных AssetInfo."""
        selected = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.Checked:
                selected.append(item.data(Qt.UserRole))
        return selected
