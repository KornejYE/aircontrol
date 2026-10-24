"""AirControl: an independent local gesture controller."""
from core.room_app_identity import reexec_named_host
reexec_named_host("AirControl", "AIRCONTROL_APP")
import argparse
import base64
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QLockFile,Qt,QTimer
from PyQt6.QtGui import QAction,QDesktopServices,QFont,QIcon,QKeySequence,QPixmap
from PyQt6.QtWidgets import (QApplication,QCheckBox,QComboBox,QFrame,QHBoxLayout,
    QLabel,QMainWindow,QMenu,QMessageBox,QPushButton,QSizePolicy,QSystemTrayIcon,
    QVBoxLayout,QWidget)
from PyQt6.QtCore import QUrl
from core.room_paths import DATA_DIR
from core.preferences import load_preferences,save_preferences
from core.room_gesture_panel import install_controller,open_panel
from core.room_settings_shell import STYLE

ROOT=Path(__file__).resolve().parents[1]
APP_VERSION='1.4.1'

class Preview(QLabel):
    def __init__(self):
        super().__init__();self.frame=QPixmap();self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(480,270);self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.setAccessibleName('Изображение камеры с точками рук')
        self.setStyleSheet('background:#101517;border:1px solid #323b40;border-radius:16px;color:#a3afb5;font-size:18px;')
        self.setText('Включите управление\nКамера и точки рук появятся здесь')
    def show_frame(self,data):
        frame=QPixmap()
        if frame.loadFromData(data):self.frame=frame;self.render()
    def render(self):
        if not self.frame.isNull():self.setPixmap(self.frame.scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
    def reset(self):
        self.frame=QPixmap();self.clear();self.setText('Управление выключено\nКамера не используется')
    def resizeEvent(self,event):super().resizeEvent(event);self.render()

class AirControlWindow(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('AirControl');self.resize(1120,800);self.setMinimumSize(920,680)
        self.setWindowIcon(QIcon(str(ROOT/'Source/assets/aircontrol.svg')))
        self._quit=False;self._last_mode=None
        body=QWidget();self.setCentralWidget(body);layout=QVBoxLayout(body);layout.setContentsMargins(28,24,28,22);layout.setSpacing(18)
        header=QHBoxLayout();heading=QVBoxLayout();title=QLabel('AirControl');title.setStyleSheet('font-size:30px;font-weight:600;');heading.addWidget(title)
        subtitle=QLabel('Управляйте компьютером движением руки · '+APP_VERSION);subtitle.setStyleSheet('color:#a3afb5;font-size:16px;');heading.addWidget(subtitle);header.addLayout(heading,1)
        self.start_button=QPushButton('Включить управление');self.start_button.setObjectName('SettingsDone');self.start_button.setMinimumHeight(48);self.start_button.clicked.connect(self.toggle);header.addWidget(self.start_button)
        settings=QPushButton('Настройки');settings.setMinimumHeight(48);settings.clicked.connect(self.settings);header.addWidget(settings);layout.addLayout(header)
        tools=QHBoxLayout();self.mode=QComboBox();self.mode.setAccessibleName('Режим управления');self.mode.setMinimumWidth(330)
        for text,mode in [('Мышь рукой · весь компьютер' if sys.platform=='win32' else 'Мышь рукой · весь Mac','system_mouse'),('Обычные жесты','discrete'),('Аналоговая прокрутка','analog'),('Мышь рукой · браузер','mouse'),('Игровой джойстик','joystick')]:self.mode.addItem(text,mode)
        self.mode.currentIndexChanged.connect(self.change_mode);tools.addWidget(self.mode)
        self.fps=QLabel('Камера выключена');self.fps.setStyleSheet('color:#a3afb5;font-size:15px;');tools.addWidget(self.fps,1,Qt.AlignmentFlag.AlignRight);layout.addLayout(tools)
        self.preview=Preview();preview_row=QHBoxLayout();preview_row.setSpacing(18);preview_row.addWidget(self.preview,1);layout.addLayout(preview_row,1)
        from core.room_joystick_panel import StickMeter
        self.state=QLabel('Готово к работе');self.state.setWordWrap(True);self.state.setAccessibleName('Состояние распознавания');self.state.setStyleSheet('font-size:17px;color:#c7d3d6;');layout.addWidget(self.state)
        self.hint=QLabel();self.hint.setWordWrap(True);self.hint.setStyleSheet('font-size:15px;color:#a3afb5;');layout.addWidget(self.hint)
        footer=QHBoxLayout();self.background=QCheckBox('Продолжать после закрытия окна');self.background.setChecked(False);footer.addWidget(self.background);footer.addStretch()
        browser=QPushButton('Подключить браузер');browser.clicked.connect(self.connect_browser);footer.addWidget(browser)
        help_button=QPushButton('Как пользоваться');help_button.clicked.connect(lambda:self.settings('guide'));footer.addWidget(help_button);layout.addLayout(footer)
        install_controller(self);self.controller=self._gesture_controller;self.controller.message.connect(self.receive)
        self.game_tools=QFrame();self.game_tools.setFixedWidth(330);game_column=QVBoxLayout(self.game_tools);game_column.setContentsMargins(0,0,0,0)
        self.stick=StickMeter(self.controller);self.stick.setMinimumHeight(240);game_column.addWidget(self.stick,1)
        from core.room_object_picker import pick_object
        self.object_pick=QPushButton('Выбрать ручку без метки');self.object_pick.clicked.connect(lambda:pick_object(self));game_column.addWidget(self.object_pick)
        self.object_neutral=QPushButton('Новая нейтраль · через 5 секунд');self.object_neutral.clicked.connect(self.recenter_object);game_column.addWidget(self.object_neutral)
        self.object_pause=QPushButton('Остановить джойстик');self.object_pause.clicked.connect(self.pause_object);game_column.addWidget(self.object_pause)
        self.game_settings=QPushButton('Настроить джойстик');self.game_settings.clicked.connect(lambda:self.settings('games'));game_column.addWidget(self.game_settings);preview_row.addWidget(self.game_tools)
        self.refresh_timer=QTimer(self);self.refresh_timer.setInterval(200);self.refresh_timer.timeout.connect(self.refresh);self.refresh_timer.start()
        self.create_tray();self.refresh()
        shortcut=QAction('Настройки',self);shortcut.setShortcut(QKeySequence.StandardKey.Preferences);shortcut.triggered.connect(self.settings);self.addAction(shortcut)
    def create_tray(self):
        self.tray=QSystemTrayIcon(self.windowIcon(),self);self.tray.setToolTip('AirControl · жесты')
        menu=QMenu();show=menu.addAction('Открыть AirControl');show.triggered.connect(self.reveal)
        self.tray_control=menu.addAction('Включить управление');self.tray_control.triggered.connect(self.toggle)
        stop=menu.addAction('Остановить управление');stop.triggered.connect(self.stop)
        menu.addSeparator();quit_action=menu.addAction('Выйти');quit_action.triggered.connect(self.quit)
        self.tray.setContextMenu(menu);self.tray.activated.connect(lambda reason:self.reveal() if reason==QSystemTrayIcon.ActivationReason.DoubleClick else None)
        if QSystemTrayIcon.isSystemTrayAvailable():self.tray.show()
    def reveal(self):self.showNormal();self.raise_();self.activateWindow()
    def settings(self,section=None):
        view=open_panel(self,section=section if isinstance(section,str) else None);view.setWindowTitle('AirControl · Настройки');return view
    def change_mode(self):
        if not hasattr(self,'controller'):return
        try:self.controller.set_mode(self.mode.currentData())
        except Exception as error:self.controller.status=str(error)
        self.refresh()
    def toggle(self):
        try:
            if self.controller.camera_snapshot()['running']:self.stop();return
            self.controller.start();self.controller.status='Запускаю камеру…'
        except Exception as error:self.controller.status=str(error)
        self.refresh()
    def stop(self):
        self.controller.stop();self.preview.reset();self.refresh()
    def recenter_object(self):
        try:self.controller.object_neutral()
        except Exception as error:self.controller.status=str(error)
    def pause_object(self):
        try:self.controller.pause_object()
        except Exception as error:self.controller.status=str(error)
    def quit(self):self._quit=True;self.controller.shutdown();QApplication.instance().quit()
    def refresh(self):
        c=self.controller;status=c.camera_snapshot();running=status['running']
        self.start_button.setText('Выключить управление' if running else 'Включить управление')
        self.tray_control.setText(self.start_button.text());self.mode.blockSignals(True)
        self.mode.setCurrentIndex(self.mode.findData(c.effective_mode));self.mode.blockSignals(False)
        self.fps.setText(c.performance or ('Камера запускается…' if running else 'Камера выключена'))
        self.state.setText(c._pointer_error or c.status)
        current=c.effective_mode
        self.game_tools.setVisible(current=='joystick')
        if current in ('mouse','system_mouse'):
            self.hint.setText('Кисть — курсор  ·  Большой + указательный — клик и перетаскивание  ·  Три пальца — прокрутка\nБольшой + средний — правый клик  ·  Кулак — остановка  ·  Esc — отключить мышь рукой')
        elif current=='joystick':
            from core.room_gesture_rules import read_settings
            game=c._game_input.config if c._game_input else read_settings(DATA_DIR/'config/gesture-actions.json')['joystick']
            self.object_neutral.setVisible(game['source']=='object');self.object_pause.setVisible(game['source']=='object')
            grip='Кулак на столе' if game['grip']=='fist' else 'Щипок большого и указательного'
            motion='наклоняйте кисть как джойстик' if game['motion']=='tilt' else 'перемещайте кисть от точки захвата'
            if game['source']=='object':self.hint.setText('Выделите конец ручки кнопкой справа · Через 5 секунд её положение станет нейтралью\nДвигайте видимый конец ручки · Esc или «Остановить джойстик» — остановка · После смены окна верните ручку в нейтраль')
            else:self.hint.setText(grip+' · Удержите 0,2 секунды, затем '+motion+'\nРаскройте руку — остановка · Esc — отключить · Хват и движение меняются в настройках джойстика')
        else:self.hint.setText('Сомкните три пальца и потяните  ·  Открытая ладонь на 1 секунду — пауза\nУголок левой рукой — громкость  ·  Для управления вкладками подключите браузер')
        if not running and not self.preview.frame.isNull():self.preview.reset()
    def receive(self,data):
        if data.get('_epoch',self.controller.epoch)!=self.controller.epoch:return
        if data.get('type')=='preview':
            try:self.preview.show_frame(base64.b64decode(data['image'],validate=True))
            except (KeyError,ValueError):pass
        self.refresh()
    def connect_browser(self):
        dialog=QMessageBox(self);dialog.setWindowTitle('AirControl · Браузер');dialog.setText('Подключение Chrome или Edge')
        dialog.setInformativeText('Откройте страницу расширений и включите режим разработчика. Нажмите «Загрузить распакованное расширение» и выберите папку BrowserGestures.\n\nВ расширении AirControl нажмите «Включить управление». Камера включится автоматически.\n\nПапка: '+str(ROOT/'BrowserGestures'))
        folder=dialog.addButton('Открыть папку расширения',QMessageBox.ButtonRole.ActionRole)
        extensions=dialog.addButton('Открыть расширения Chrome',QMessageBox.ButtonRole.ActionRole)
        dialog.addButton('Готово',QMessageBox.ButtonRole.AcceptRole)
        folder.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(ROOT/'BrowserGestures'))))
        extensions.clicked.connect(lambda:QDesktopServices.openUrl(QUrl('chrome://extensions/')))
        dialog.exec()
    def closeEvent(self,event):
        if not self._quit and self.background.isChecked() and self.tray.isVisible():event.ignore();self.hide();return
        self.controller.shutdown();event.accept();QApplication.instance().quit()

def main():
    if sys.platform=='win32':
        from core.room_windows_input import initialize_windows
        initialize_windows()
    parser=argparse.ArgumentParser();parser.add_argument('--render-preview',type=Path);args=parser.parse_args()
    DATA_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
    app=QApplication(sys.argv[:1]);app.setApplicationName('AirControl');app.setOrganizationName('AirControl');app.setApplicationVersion(APP_VERSION);app.setStyleSheet(STYLE);app.setFont(QFont('Arial',16))
    lock=QLockFile(str(DATA_DIR/'aircontrol.lock'));lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None,'AirControl','AirControl уже запущен. Откройте его из Dock или строки меню.');return 0
    window=AirControlWindow();window.show()
    if args.render_preview:
        args.render_preview.parent.mkdir(parents=True,exist_ok=True)
        def render():window.grab().save(str(args.render_preview));window.quit()
        QTimer.singleShot(150,render)
    return app.exec()

if __name__=='__main__':raise SystemExit(main())
