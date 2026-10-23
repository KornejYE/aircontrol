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
        by_object=self.controller.game_config['source']=='object'
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#25d4dc' if active else '#77898f'))
        p.drawEllipse(QRectF(cx+x*radius-7, cy+y*radius-7, 14, 14))
        p.setPen(QColor('#d7e4e7'))
        p.drawText(QRectF(162, 16, max(0, self.width()-172), self.height()-20),
                   Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
                   f'X {x:+.2f}    Y {y:+.2f}\n' + (self.controller.joystick_status or
                   ('Выберите ручку на камере' if by_object and self.controller.ready else 'Покажите выбранный хват' if self.controller.ready else 'Включите камеру · ввод в игру не выполняется')) +
                   ('\nПредмет отслеживается' if active and by_object else '\nХват активен' if active else '\nНейтраль задаётся кнопкой ниже' if by_object else '\nРаскройте руку · следующий хват задаст нейтраль'))


def install_game_settings(panel):
    from core.room_gesture_panel import DATA_DIR
    from core.room_gesture_rules import read_settings, save_settings
    from core.room_game_input import running_games

    workspace = panel.settings_workspace
    path = DATA_DIR / 'config/gesture-actions.json'
    config = read_settings(path)['joystick']
    workspace.add_page('games', 'Игровой джойстик', 'Ручное управление кистью. Не является виртуальным геймпадом.')
    frame, box = card('Джойстик рукой',
        'По умолчанию: поставьте кулак ребром на стол, подержите прямо 0,2 секунды и наклоняйте '
        'вправо, влево, вперёд и назад, как ручку джойстика. Раскройте ладонь или уберите руку для остановки. '
        'Esc останавливает до повторного включения управления. Щипок и перемещение всей кисти доступны ниже.')
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
    source = QComboBox();source.setAccessibleName('Что отслеживать для джойстика')
    source.addItem('Рука · кулак или щипок','hand');source.addItem('Обычная ручка · выбрать на изображении','object')
    source.setCurrentIndex(source.findData(config['source']));tune.insertWidget(2,source)
    from core.room_object_picker import pick_object
    choose=QPushButton('Выбрать ручку без метки');choose.clicked.connect(lambda:pick_object(panel.parentWidget()));tune.addWidget(choose)
    grip = QComboBox();grip.setAccessibleName('Хват игрового джойстика')
    grip.addItem('Кулак · как ручка джойстика','fist');grip.addItem('Щипок большого и указательного','pinch')
    grip.setCurrentIndex(grip.findData(config['grip']));tune.addWidget(grip)
    motion = QComboBox();motion.setAccessibleName('Движение игрового джойстика')
    motion.addItem('Наклон кисти · можно опираться на стол','tilt');motion.addItem('Перемещение всей кисти','translate')
    motion.setCurrentIndex(motion.findData(config['motion']));tune.addWidget(motion)

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
    tilt = slider('Наклон до полного отклонения', 10, 60, round(config['tilt_degrees']), lambda v: f'{v}°')
    object_span = slider('Размах движения ручки', 3, 60, round(config['object_span']*100), lambda v: f'{v}% высоты кадра')
    deadzone = slider('Мёртвая зона', 5, 40, round(config['deadzone']*100), lambda v: f'{v}%')
    mouse_range = slider('Радиус мыши-джойстика', 10, 45, round(config['mouse_range']*100), lambda v: f'{v}% короткой стороны экрана')
    invert = QCheckBox('Инвертировать вертикальную ось')
    invert.setChecked(config['invert_y'])
    tune.addWidget(invert)
    def motion_controls():
        by_hand=source.currentData()=='hand'
        radius.setEnabled(by_hand and motion.currentData()=='translate');tilt.setEnabled(by_hand and motion.currentData()=='tilt')
        object_span.setEnabled(not by_hand)
        for control in (hand,grip,motion):control.setEnabled(by_hand)
    motion.currentIndexChanged.connect(motion_controls);source.currentIndexChanged.connect(motion_controls);motion_controls()

    syncing = False
    def save():
        if syncing:return
        current = read_settings(path)
        current['joystick'] = dict(output=output.currentData(), target=target.currentData() or '',
                                  hand=hand.currentData(), radius=radius.value()/100,
                                  grip=grip.currentData(),motion=motion.currentData(),tilt_degrees=tilt.value(),
                                  source=source.currentData(),object_span=object_span.value()/100,
                                  deadzone=deadzone.value()/100, mouse_range=mouse_range.value()/100,
                                  invert_y=invert.isChecked())
        save_settings(path, current)
        panel.bindings = read_settings(path)
        panel.controller.reload_rules()
    for combo in (output, target, hand, grip, motion, source):
        combo.currentIndexChanged.connect(save)
    for control in (radius, deadzone, mouse_range, tilt, object_span):
        control.valueChanged.connect(save)
    invert.toggled.connect(save)

    for title, keywords, control in [
        ('Вывод джойстика', 'war thunder вар тандер танки самолёты wasd игра клавиатура', output),
        ('Что отслеживать для джойстика', 'ручка предмет без метки рука камера', source),
        ('Выбрать ручку без метки', 'предмет колпачок трекер камера', choose),
        ('Размах движения ручки', 'чувствительность предмет расстояние', object_span),
        ('Выбрать игру', 'war thunder вар тандер передний план фокус', target),
        ('Рука джойстика', 'правая левая', hand),
        ('Хват джойстика', 'кулак ребро стол щипок', grip),
        ('Движение джойстика', 'наклон поворот перемещение кисти', motion),
        ('Угол наклона джойстика', 'чувствительность градусы', tilt),
        ('Размах джойстика', 'чувствительность радиус', radius),
        ('Мёртвая зона джойстика', 'дрожание нейтраль', deadzone),
        ('Инверсия джойстика', 'ось вверх вниз', invert),
    ]:
        workspace.register(title, 'games', keywords, control)
    panel.game_output = output
    panel.game_target = target
    panel.game_radius = radius
    panel.game_hand = hand
    panel.game_source = source
    panel.game_grip = grip;panel.game_motion = motion
    def sync():
        nonlocal syncing
        syncing = True
        try:
            saved = read_settings(path)['joystick']
            if target.findData(saved['target'])<0:target.addItem(saved['target'],saved['target'])
            for control, value in ((output,saved['output']),(target,saved['target']),(hand,saved['hand']),(grip,saved['grip']),(motion,saved['motion']),(source,saved['source'])):
                control.setCurrentIndex(control.findData(value))
            radius.setValue(round(saved['radius']*100));deadzone.setValue(round(saved['deadzone']*100))
            mouse_range.setValue(round(saved['mouse_range']*100));invert.setChecked(saved['invert_y'])
            tilt.setValue(round(saved['tilt_degrees']))
            object_span.setValue(round(saved['object_span']*100))
        finally:syncing = False
    panel.sync_game_settings = sync
