"""Organize existing gesture controls without replacing their signal handlers."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel,QPushButton,QHBoxLayout
from core.room_settings_shell import STYLE
from core.room_settings_workspace import SettingsWorkspace,card
from core.room_gesture_rules import EVENTS


def _hide(layout):
    while layout.count():
        item=layout.takeAt(0)
        if item.widget():item.widget().hide()
        elif item.layout():_hide(item.layout())


def install(panel):
    done=next(b for b in panel.findChildren(QPushButton) if b.accessibleName()=='Закрыть настройки жестов')
    root=panel.layout();_hide(root)
    panel.setWindowTitle('Настройки · Жесты и мышь');panel.setMinimumSize(820,600);panel.resize(1060,780);panel.setStyleSheet(STYLE)
    root.setContentsMargins(22,20,22,16);root.setSpacing(16)
    header=QHBoxLayout();title=QLabel('Жесты и мышь');title.setStyleSheet('font-size:28px;font-weight:600;');header.addWidget(title,1)
    panel.toggle.setObjectName('SettingsDone');header.addWidget(panel.toggle);panel.toggle.show();header.addWidget(done);done.show();root.addLayout(header)
    workspace=SettingsWorkspace(panel,'Найти: скорость, ускорение, размах, левая рука…');panel.settings_workspace=workspace;root.addWidget(workspace,1)
    sections=[('overview','Начало','Режим управления и быстрые переходы.'),('mouse','Мышь и курсор','Чувствительность, управляющая рука и ускорение.'),('scroll','Прокрутка','Размах, воспроизведение и управление браузером.'),('bindings','Назначения','Любое действие для правой и левой руки.'),('camera','Камера','Изображение, выбор устройства и распознавание.'),('guide','Как пользоваться','Текстовые инструкции для всех жестов.')]
    for key,title,description in sections:workspace.add_page(key,title,description)
    from core.room_joystick_panel import install_game_settings
    install_game_settings(panel)
    destinations={'Режим управления':'overview','Мышь рукой':'mouse','Назначения жестов':'bindings','Камера':'camera','Пауза и воспроизведение':'scroll','Захватите и потяните':'scroll','Подстройте под себя':'scroll','Подключите страницу':'scroll'}
    for title,frame in panel._settings_cards.items():
        frame.setObjectName('SettingsCard');workspace.add(destinations[title],frame)
    # Move the existing guide out of its old tab before that hidden tab is reused.
    old_pages=panel.pages;old_pages.removeTab(old_pages.indexOf(panel.guide));workspace.add('guide',panel.guide)
    quick,box=card('Что настроить?','Частые параметры — в одном переходе.')
    for label,description,key in [('Мышь и курсор','Скорость, ускорение и выбор руки','mouse'),('Прокрутка','Размах свайпа и управление видео','scroll'),('Игровой джойстик','War Thunder, WASD и мышь-джойстик','games'),('Камера','Превью и выбор камеры','camera'),('Назначения','Что выполняет каждый жест','bindings')]:
        row=QPushButton(label+'  →');row.setToolTip(description);row.clicked.connect(lambda checked=False,k=key:workspace.select(k));box.addWidget(row)
    workspace.add('overview',quick)
    for key,title,description in sections:workspace.register(title,key,description)
    for title,page,keywords,target in [
        ('Режим управления','overview','обычный аналоговый мышь браузер весь mac',panel.mode_combo),
        ('Скорость курсора','mouse','dpi дпи ди пи ай чувствительность мыши',panel.mouse_speed),
        ('Ускорение курсора','mouse','dpi дпи ди пи ай быстро медленно скорость',panel.mouse_acceleration),
        ('Точное наведение','mouse','медленно маленькие кнопки чувствительность дрожь стабилизация',panel.mouse_precision),
        ('Правая или левая рука для мыши','mouse','управляющая рука',panel.mouse_hand),
        ('Относительное или прямое наведение','mouse','позиционирование тачпад указатель',panel.mouse_position),
        ('Размах движения','scroll','длина маха чувствительность свайп шортс shorts аналоговый',panel.distance),
        ('Управлять видео в браузере','scroll','пауза громкость масштаб chrome edge игра',panel.browser_media),
        ('Включать камеру при запуске','scroll','автозапуск жестов',panel.always),
        ('Поменять левую и правую руку','bindings','инверсия зеркальность',panel.swap_hands),
        ('Номер камеры','camera','устройство вебкамера emeet',panel.camera),
    ]:workspace.register(title,page,keywords,target)
    for hand,event,combo in panel.binding_combos:
        label=('Правая' if hand=='Right' else 'Левая')+' рука · '+EVENTS[event]
        workspace.register(label,'bindings',lambda c=combo,e=event:EVENTS[e]+' '+c.currentText(),combo,lambda h=hand:panel.binding_tabs.setCurrentIndex(0 if h=='Right' else 1))
    for title,page in [('Настроить захват · 10 секунд','scroll'),('Вернуть стандартные жесты','bindings'),('Открыть расширение для Chrome / Edge','scroll')]:
        button=next((b for b in panel.findChildren(QPushButton) if b.text()==title),None)
        if button:workspace.register(title,page,'обучение калибровка' if 'захват' in title else '',button)
    footer=QLabel('Изменения сохраняются сразу  ·  Ctrl/Cmd + F — поиск  ·  Камера управляется кнопкой сверху');footer.setWordWrap(True);footer.setStyleSheet('font-size:14px;color:#a3afb5;');root.addWidget(footer)
    panel.pages=workspace.stack;panel.scroll=workspace.sections['bindings']['scroll']
    workspace.select('mouse' if panel.controller.control_mode in ('mouse','system_mouse') else 'overview')
