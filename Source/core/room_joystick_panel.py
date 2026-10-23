"""Readable game-stick settings and a live, local axis meter."""
from PyQt6.QtCore import Qt, QRectF, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QSlider, QWidget

from core.room_settings_workspace import card


class StickMeter(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setMinimumHeight(158)
        self.setAccessibleName('Отклонение игрового джойстика')
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.update)
        self.timer.start()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = min(58., (self.height() - 30) / 2)
        cx, cy = 80., self.height() / 2
        p.setPen(QPen(QColor('#35454b'), 2))
        p.setBrush(QColor('#10191c'))
        p.drawEllipse(QRectF(cx-radius, cy-radius, radius*2, radius*2))
        p.drawLine(int(cx-radius), int(cy), int(cx+radius), int(cy))
        p.drawLine(int(cx), int(cy-radius), int(cx), int(cy+radius))
        data = self.controller.joystick_data
        x, y = data.get('x', 0), data.get('y', 0)
        active = data.get('active', False)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#25d4dc' if active else '#77898f'))
        p.drawEllipse(QRectF(cx+x*radius-7, cy+y*radius-7, 14, 14))
        p.setPen(QColor('#d7e4e7'))
        p.drawText(QRectF(162, 16, max(0, self.width()-172), self.height()-20),
                   Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
                   f'X {x:+.2f}    Y {y:+.2f}\n' + (self.controller.joystick_status or
                   ('Сомкните пальцы для нового захвата' if self.controller.ready else 'Включите камеру · ввод в игру не выполняется')) +
                   ('\nЗахват активен' if active else '\nРазожмите пальцы · новый захват задаёт нейтраль'))


def install_game_settings(panel):
    from core.room_gesture_panel import DATA_DIR
    from core.room_gesture_rules import read_settings, save_settings
    from core.room_game_input import running_games

    workspace = panel.settings_workspace
    path = DATA_DIR / 'config/gesture-actions.json'
    config = read_settings(path)['joystick']
    workspace.add_page('games', 'Игровой джойстик', 'Ручное управление кистью. Не является виртуальным геймпадом.')
    frame, box = card('Джойстик рукой',
        'Сведите большой и указательный пальцы, удержите 0,2 секунды и двигайте кисть. '
        'Точка захвата становится нейтралью. Разожмите пальцы или уберите руку — ввод отпускается. '
        'Кулак не включает джойстик. Esc останавливает до повторного включения управления.')
    workspace.add('games', frame)
    box.addWidget(StickMeter(panel.controller))
    mode = QPushButton('Выбрать режим «Игровой джойстик»')
    mode.clicked.connect(lambda: panel.controller.set_mode('joystick'))
    box.addWidget(mode)

    output = QComboBox()
    output.setAccessibleName('Вывод игрового джойстика')
    for title, value in [('Проверка на экране · без ввода в игру', 'preview'),
                         ('Танки · клавиши WASD', 'wasd'),
                         ('Самолёты · мышь-джойстик', 'mouse')]:
        output.addItem(title, value)
    output.setCurrentIndex(output.findData(config['output']))
    box.addWidget(output)
    note = QLabel('WASD передаёт четыре обычные клавиши, включая диагонали, без повторяющихся макросов. '
                  'Для самолётов выберите «Мышь-джойстик» в настройках War Thunder, разверните игру на весь экран '
                  'и оставьте нейтраль джойстика в центре экрана. '
                  'Это движение системной мыши, не отдельный аналоговый HID-контроллер. Стрельба остаётся у вас.')
    note.setWordWrap(True)
    box.addWidget(note)
    compatibility = QLabel('Совместимость с античитом War Thunder не подтверждена. '
                           'Отсутствие блокировки аккаунта не гарантируется. Подробности — в README приложения.')
    compatibility.setWordWrap(True)
    box.addWidget(compatibility)

    target_row = QHBoxLayout()
    target = QComboBox()
    target.setAccessibleName('Игра для джойстика')
    refresh = QPushButton('Обновить список игр')
    target_row.addWidget(target, 1)
    target_row.addWidget(refresh)
    box.addLayout(target_row)

    def load_targets():
        saved = target.currentData() if target.count() else config['target']
        target.blockSignals(True)
        try:
            target.clear()
            target.addItem('Выберите запущенную игру…', '')
            try:
                games = running_games()
            except Exception:
                games = []
            for identifier, name in games:
                target.addItem(name + ' · ' + identifier, identifier)
            if saved and target.findData(saved) < 0:
                target.addItem(saved + ' · сейчас не запущена', saved)
            target.setCurrentIndex(max(0, target.findData(saved)))
        finally:
            target.blockSignals(False)
    load_targets()
    refresh.clicked.connect(load_targets)
    focus_note = QLabel('Ввод поступает только в выбранную игру на переднем плане. '
                        'При переходе в браузер, потере руки или зависании камеры клавиши отпускаются. '
                        'Перед возвращением в игру разожмите пальцы. В самолётном режиме физическая мышь имеет приоритет.')
    focus_note.setWordWrap(True)
    box.addWidget(focus_note)

    tuning, tune = card('Рука и чувствительность', 'Настройки джойстика сохраняются отдельно от мыши и прокрутки.')
    workspace.add('games', tuning)
    hand = QComboBox()
    hand.setAccessibleName('Управляющая рука для джойстика')
    hand.addItem('Правая рука', 'Right')
    hand.addItem('Левая рука', 'Left')
    hand.setCurrentIndex(hand.findData(config['hand']))
    tune.addWidget(hand)

    def slider(title, low, high, initial, label):
        caption = QLabel()
        control = QSlider(Qt.Orientation.Horizontal)
        control.setRange(low, high)
        control.setValue(initial)
        control.setAccessibleName(title)
        control.valueChanged.connect(lambda value: caption.setText(title + ' · ' + label(value)))
        caption.setText(title + ' · ' + label(initial))
        tune.addWidget(caption)
        tune.addWidget(control)
        return control
    radius = slider('Размах до полного отклонения', 60, 300, round(config['radius']*100), lambda v: f'{v/100:g} ширины ладони')
    deadzone = slider('Мёртвая зона', 5, 40, round(config['deadzone']*100), lambda v: f'{v}%')
    mouse_range = slider('Радиус мыши-джойстика', 10, 45, round(config['mouse_range']*100), lambda v: f'{v}% короткой стороны экрана')
    invert = QCheckBox('Инвертировать вертикальную ось')
    invert.setChecked(config['invert_y'])
    tune.addWidget(invert)

    syncing = False
    def save():
        if syncing:return
        current = read_settings(path)
        current['joystick'] = dict(output=output.currentData(), target=target.currentData() or '',
                                  hand=hand.currentData(), radius=radius.value()/100,
                                  deadzone=deadzone.value()/100, mouse_range=mouse_range.value()/100,
                                  invert_y=invert.isChecked())
        save_settings(path, current)
        panel.bindings = read_settings(path)
        panel.controller.reload_rules()
    for combo in (output, target, hand):
        combo.currentIndexChanged.connect(save)
    for control in (radius, deadzone, mouse_range):
        control.valueChanged.connect(save)
    invert.toggled.connect(save)

    for title, keywords, control in [
        ('Вывод джойстика', 'war thunder вар тандер танки самолёты wasd игра клавиатура', output),
        ('Выбрать игру', 'war thunder вар тандер передний план фокус', target),
        ('Рука джойстика', 'правая левая', hand),
        ('Размах джойстика', 'чувствительность радиус', radius),
        ('Мёртвая зона джойстика', 'дрожание нейтраль', deadzone),
        ('Инверсия джойстика', 'ось вверх вниз', invert),
    ]:
        workspace.register(title, 'games', keywords, control)
    panel.game_output = output
    panel.game_target = target
    panel.game_radius = radius
    panel.game_hand = hand
    def sync():
        nonlocal syncing
        syncing = True
        try:
            saved = read_settings(path)['joystick']
            if target.findData(saved['target'])<0:target.addItem(saved['target'],saved['target'])
            for control, value in ((output,saved['output']),(target,saved['target']),(hand,saved['hand'])):
                control.setCurrentIndex(control.findData(value))
            radius.setValue(round(saved['radius']*100));deadzone.setValue(round(saved['deadzone']*100))
            mouse_range.setValue(round(saved['mouse_range']*100));invert.setChecked(saved['invert_y'])
        finally:syncing = False
    panel.sync_game_settings = sync
