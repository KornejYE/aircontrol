"""Choose the number and exact subset of attached displays; no camera/input."""
from PyQt6.QtWidgets import QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget
from core.room_pointer_area import display_options, display_target, selected_display_ids


class DisplayPicker(QDialog):
    def __init__(self, parent, target='all', options_provider=display_options):
        super().__init__(parent)
        self.provider = options_provider
        self.initial_target = display_target(target)
        self.automatic = self.initial_target == 'all'
        self.checks = {}
        self.options = []
        self.setWindowTitle('Экраны для управления · AirControl')
        self.resize(670, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel('Сколько экранов использовать?')
        title.setStyleSheet('font-size:24px;font-weight:600;')
        layout.addWidget(title)
        note = QLabel('Выберите количество и отметьте нужные мониторы. Их размеры и расположение берутся из системы. '
                      'Режим «Автоматически» использует все подключённые экраны, включая добавленные позже.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.count = QComboBox()
        self.count.setAccessibleName('Количество экранов для управления')
        self.count.currentIndexChanged.connect(self.count_changed)
        layout.addWidget(self.count)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        refresh = QPushButton('Обновить список экранов')
        refresh.clicked.connect(self.refresh)
        buttons.addWidget(refresh)
        buttons.addStretch()
        cancel = QPushButton('Отмена')
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.save = QPushButton('Использовать эти экраны')
        self.save.setObjectName('SettingsDone')
        self.save.clicked.connect(self.accept)
        buttons.addWidget(self.save)
        layout.addLayout(buttons)
        self.refresh()

    def selected_keys(self):
        return [key for key, check in self.checks.items() if check.isChecked()]

    def target(self):
        if self.automatic:
            return 'all'
        keys = self.selected_keys()
        if len(keys) == 1:
            return keys[0]
        return display_target('displays:' + ','.join(key[8:] for key in keys))

    def refresh(self):
        previous = set(self.selected_keys()) if self.checks else {f'display:{i}' for i in selected_display_ids(self.initial_target)}
        self.options = self.provider()
        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(8, 8, 8, 8)
        self.checks = {}
        for key, title, (x, y, w, h) in self.options:
            check = QCheckBox(title + f'  ·  положение {int(x)}, {int(y)}')
            check.setAccessibleName(title)
            check.setChecked(self.automatic or key in previous)
            check.toggled.connect(self.check_changed)
            column.addWidget(check)
            self.checks[key] = check
        column.addStretch()
        old = self.scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self.scroll.setWidget(body)
        self.count.blockSignals(True)
        self.count.clear()
        self.count.addItem('Автоматически · все подключённые', 0)
        for number in range(1, len(self.options) + 1):
            self.count.addItem(str(number), number)
        self.count.setEnabled(bool(self.options))
        self.count.setCurrentIndex(0 if self.automatic else self.count.findData(len(self.selected_keys())) if self.selected_keys() else -1)
        self.count.blockSignals(False)
        self.update_status()

    def count_changed(self):
        number = self.count.currentData()
        if number is None:
            return
        self.automatic = number == 0
        order = self.selected_keys() + [key for key in self.checks if key not in self.selected_keys()]
        selected = set(self.checks if self.automatic else order[:number])
        for key, check in self.checks.items():
            check.blockSignals(True)
            check.setChecked(key in selected)
            check.blockSignals(False)
        self.update_status()

    def check_changed(self):
        self.automatic = False
        number = len(self.selected_keys())
        self.count.blockSignals(True)
        self.count.setCurrentIndex(self.count.findData(number) if number else -1)
        self.count.blockSignals(False)
        self.update_status()

    def update_status(self):
        number = len(self.selected_keys())
        self.save.setEnabled(number > 0)
        self.status.setText(f'Подключено: {len(self.options)}. Выбрано: {number}.' +
                            (' Будут использоваться все подключённые экраны.' if self.automatic and number else '') +
                            (' Выберите хотя бы один экран.' if not number else ''))
