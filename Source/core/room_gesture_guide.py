"""Text-only, offline reference for every configurable gesture event."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QLineEdit, QComboBox, QPushButton, QScrollArea,
    QSizePolicy)
from core.room_shell import BG, EDGE, CYAN, TEXT, BUTTON
from core.room_gesture_rules import EVENTS, ACTIONS, read_settings
from core.room_paths import DATA_DIR

DIRECTIONS = {'up': 'вверх', 'down': 'вниз', 'left': 'влево', 'right': 'вправо'}
INSTRUCTIONS = {
    'grab': ('Захват тремя пальцами',
             'Соедините кончики большого, указательного и среднего пальцев. '
             'Согните их в захват; безымянный и мизинец тоже согните.',
             'Сразу потяните всю кисть {direction}. Можно войти в кадр уже с захватом.',
             'Разожмите пальцы перед следующим движением.'),
    'corner': ('Уголок',
               'Выпрямите указательный палец. Отведите большой в сторону, чтобы получилась буква L. '
               'Средний, безымянный и мизинец согните.',
               'Зафиксируйте кисть примерно на четверть секунды, затем двигайте всю кисть {direction}. '
               'Сохраняйте форму уголка.',
               'Для следующего шага громкости можно продолжить движение, сохраняя уголок.'),
    'pinch': ('Щипок двумя пальцами',
              'Соедините только большой и указательный пальцы. '
              'Средний, безымянный и мизинец согните к ладони.',
              'Удерживая щипок, потяните всю кисть {direction}. Расстояние между пальцами не меняйте.',
              'Разожмите щипок перед повтором. Этот жест нужно назначить в настройках.'),
    'point': ('Указательный палец',
              'Поднимите только указательный палец. Большой и остальные три пальца согните.',
              'Сохраняя эту форму, двигайте всю кисть {direction}.',
              'Смените положение пальцев перед повтором. По умолчанию действие не назначено.'),
    'palm': ('Открытая ладонь',
             'Раскройте все пять пальцев и поверните ладонь к камере. Кисть можно наклонить.',
             'Держите кисть неподвижно одну секунду. Двигать её не нужно.',
             'Опустите руку или уберите её из кадра, затем покажите ладонь снова. '
             'После свайпа тоже удерживайте раскрытую ладонь целую секунду.'),
    'fist': ('Кулак',
             'Согните все пальцы в кулак. Большой палец прижмите к остальным.',
             'Держите кулак неподвижно около секунды.',
             'Разожмите кулак перед повтором. По умолчанию действие не назначено.'),
    'thumb_up': ('Большой палец вверх',
                 'Сожмите четыре пальца в кулак. Большой палец выпрямите и направьте вверх.',
                 'Удерживайте кисть неподвижно около секунды.',
                 'Смените положение пальцев перед повтором. По умолчанию действие не назначено.'),
    'thumb_down': ('Большой палец вниз',
                   'Сожмите четыре пальца в кулак. Большой палец выпрямите и направьте вниз.',
                   'Удерживайте кисть неподвижно около секунды.',
                   'Смените положение пальцев перед повтором. По умолчанию действие не назначено.'),
}


def explanation(event):
    if event in ('both_spread','both_close'):
        spread=event=='both_spread'
        return ('Обе руки · '+('увеличение' if spread else 'уменьшение'),
                'Покажите обе руки и на каждой сомкните большой и указательный пальцы. Можно также присоединить средний палец.',
                ('Разводите кисти в стороны' if spread else 'Сближайте кисти')+' одновременно, удерживая оба захвата. Камера должна видеть обе кисти.',
                'Неподвижные руки масштаб не меняют. Разожмите пальцы на обеих руках перед новым жестом. В режиме мыши для всего Mac изменяется масштаб активного приложения, в браузерном режиме — выбранной вкладки.')
    if event.startswith('zoom_'):
        spread = event == 'zoom_spread'
        return ('Развести два пальца' if spread else 'Свести два пальца',
                'Выставьте большой и указательный пальцы. Средний, безымянный и мизинец согните. '
                'Поверните ладонь к камере.',
                ('Увеличивайте' if spread else 'Уменьшайте') +
                ' расстояние между кончиками большого и указательного пальцев. Саму кисть держите на месте.',
                'Меняется расстояние между двумя пальцами — это отличается от перетаскивания всей кисти щипком.')
    pose, suffix = event.rsplit('_', 1)
    title, shape, motion, repeat = INSTRUCTIONS[pose]
    direction = DIRECTIONS.get(suffix, '')
    return title + (' · ' + direction if direction else ''), shape, motion.format(direction=direction), repeat


class GestureGuide(QWidget):
    def __init__(self, open_bindings):
        super().__init__()
        self.open_bindings = open_bindings
        self.setStyleSheet(f'QWidget{{background:transparent;color:{TEXT};font:16px Arial;}} '
            f'QListWidget{{background:{BG};border:1px solid {EDGE};border-radius:10px;outline:0;}} '
            f'QListWidget::item{{padding:12px 8px;border-radius:6px;}} '
            f'QListWidget::item:selected{{background:#293e40;color:{CYAN};}} '
            f'QLineEdit,QComboBox{{background:{BG};border:1px solid {EDGE};border-radius:8px;padding:9px;color:{TEXT};}} '+BUTTON)
        root = QHBoxLayout(self)
        root.setContentsMargins(0,14,0,0)
        root.setSpacing(18)
        navigation = QVBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Найти жест…')
        self.search.setAccessibleName('Поиск жестов в справочнике')
        self.search.setClearButtonEnabled(True)
        navigation.addWidget(self.search)
        self.list = QListWidget()
        self.list.setAccessibleName('Все доступные жесты')
        self.list.setWordWrap(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        from core.room_gesture_zoom import BIMANUAL_EVENTS
        for event,title in {**EVENTS,**BIMANUAL_EVENTS}.items():
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole,event)
            self.list.addItem(item)
        navigation.addWidget(self.list,1)
        self.empty = QLabel('Жест не найден')
        self.empty.hide()
        navigation.addWidget(self.empty)
        nav = QWidget()
        nav.setLayout(navigation)
        nav.setFixedWidth(212)
        navigation.setContentsMargins(0,0,0,0)
        root.addWidget(nav)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        detail = QWidget()
        detail.setMinimumWidth(0)
        scroll.setWidget(detail)
        box = QVBoxLayout(detail)
        box.setContentsMargins(0,0,12,12)
        box.setSpacing(14)
        self.title = QLabel()
        self.title.setWordWrap(True)
        self.title.setStyleSheet(f'font-size:24px;font-weight:600;color:{TEXT};')
        box.addWidget(self.title)
        self.motion_hint = QLabel()
        self.motion_hint.setWordWrap(True)
        self.motion_hint.setStyleSheet(f'color:{CYAN};font-size:15px;')
        box.addWidget(self.motion_hint)
        tools = QHBoxLayout()
        self.hand = QComboBox()
        self.hand.addItem('Правая рука','Right')
        self.hand.addItem('Левая рука','Left')
        self.hand.setAccessibleName('Рука для назначения жеста')
        tools.addWidget(self.hand,1)
        box.addLayout(tools)
        self.instructions = []
        for heading in ('1. Положение пальцев','2. Движение или удержание','3. Как повторить'):
            title = QLabel(heading)
            title.setStyleSheet('font-weight:600;')
            box.addWidget(title)
            text = QLabel()
            text.setWordWrap(True)
            text.setTextFormat(Qt.TextFormat.PlainText)
            text.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Minimum)
            box.addWidget(text)
            self.instructions.append(text)
        self.assignment = QLabel()
        self.assignment.setWordWrap(True)
        self.assignment.setStyleSheet(f'color:{CYAN};font-size:16px;')
        box.addWidget(self.assignment)
        configure = QPushButton('Изменить назначение')
        configure.clicked.connect(open_bindings)
        box.addWidget(configure,0,Qt.AlignmentFlag.AlignLeft)
        box.addStretch()
        root.addWidget(scroll,1)
        self.list.currentItemChanged.connect(self.select)
        self.hand.currentIndexChanged.connect(self.select)
        self.search.textChanged.connect(self.filter)
        self.list.setCurrentRow(0)

    def filter(self, value):
        terms = value.casefold().split()
        visible = []
        for index in range(self.list.count()):
            item = self.list.item(index)
            event = item.data(Qt.ItemDataRole.UserRole)
            title,shape,motion,_ = explanation(event)
            show = all(t in (item.text()+' '+title+' '+shape+' '+motion).casefold() for t in terms)
            item.setHidden(not show)
            if show:
                visible.append(item)
        self.empty.setVisible(not visible)
        current = self.list.currentItem()
        if visible and (current is None or current.isHidden()):
            self.list.setCurrentItem(visible[0])

    def select(self, *args):
        item = self.list.currentItem()
        if item is None:
            return
        event = item.data(Qt.ItemDataRole.UserRole)
        title,shape,motion,repeat = explanation(event)
        self.title.setText(title)
        both=event in ('both_spread','both_close')
        self.hand.setEnabled(not both)
        if both:
            self.motion_hint.setText('Два захвата · разведите или сблизьте обе кисти')
            for widget,text in zip(self.instructions,(shape,motion,repeat)):widget.setText(text)
            cfg=read_settings(DATA_DIR/'config/gesture-actions.json')
            self.assignment.setText('Обе руки · '+('масштабирование включено' if cfg['two_hand_zoom'] else 'масштабирование выключено в настройках мыши'))
            return
        if event.startswith('zoom_'):
            hint = 'Двигайте два пальца; кисть держите на месте'
        elif event.endswith('_hold'):
            hint = 'Удерживайте кисть неподвижно около секунды'
        else:
            direction = DIRECTIONS[event.rsplit('_',1)[1]]
            hint = ('Сначала зафиксируйте уголок на 0,25 с; затем ' if event.startswith('corner_')
                    else 'Двигайте всю кисть ') + direction
        self.motion_hint.setText(hint)
        for widget,text in zip(self.instructions,(shape,motion,repeat)):
            widget.setText(text)
        hand = self.hand.currentData()
        cfg = read_settings(DATA_DIR/'config/gesture-actions.json')
        if cfg['mode']=='analog' and (event.startswith('grab_') or (hand=='Left' and event.startswith('corner_'))):
            self.motion_hint.setText('Аналоговое: страница следует за рукой, как при прокрутке пальцем')
            self.instructions[1].setText('Захватите три пальца и плавно тяните кисть вверх или вниз. Во время движения страница следует за рукой, а обратное движение возвращает её. Для следующего Shorts нужно протянуть полный экран; ползунок «Размах на одно видео» меняет нужное расстояние. Горизонтальное движение задаёт секунды перемотки, левый уголок — изменение громкости.')
            self.instructions[2].setText('Частичное движение при отпускании возвращает текущий Shorts; полный экран переключает ровно одно видео за каждый экран. Разожмите пальцы или уберите руку для завершения. Действия идут в выбранную вкладку расширения.')
        action = cfg['rules'][hand][event]
        side = 'Правая' if hand == 'Right' else 'Левая'
        self.assignment.setText(side+' рука · '+(ACTIONS[action] if action != 'none' else 'действие пока не назначено'))

    def showEvent(self,event):
        self.select()
        super().showEvent(event)
