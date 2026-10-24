"""Choose the absolute pointer's work rectangle on the mirrored live preview."""
import base64
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget
from core.room_pointer_area import DEFAULT_AREA, pointer_area, valid_area


class AreaCanvas(QWidget):
    changed = pyqtSignal(bool)

    def __init__(self, area=None):
        super().__init__()
        self.frame = QPixmap()
        self.area = pointer_area(area)
        self.drag = None
        self.setMinimumSize(560, 315)
        self.setMouseTracking(True)
        self.setAccessibleName('Поле прямого наведения: выделите прямоугольник на изображении камеры')

    def image_rect(self):
        if self.frame.isNull():
            return QRectF()
        scale = min(self.width() / self.frame.width(), self.height() / self.frame.height())
        w, h = self.frame.width() * scale, self.frame.height() * scale
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def show_image(self, data):
        frame = QPixmap()
        try:
            if frame.loadFromData(base64.b64decode(data, validate=True)):
                self.frame = frame
                self.update()
                self.changed.emit(valid_area(self.area))
        except (TypeError, ValueError):
            pass

    def set_area(self, area):
        self.area = pointer_area(area)
        self.changed.emit(not self.frame.isNull())
        self.update()

    def pixel(self, x, y):
        image = self.image_rect()
        return QPointF(image.x() + x * image.width(), image.y() + y * image.height())

    def normalized(self, point):
        image = self.image_rect()
        return (max(0., min(1., (point.x() - image.x()) / image.width())),
                max(0., min(1., (point.y() - image.y()) / image.height())))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#101517'))
        image = self.image_rect()
        if self.frame.isNull():
            painter.setPen(QColor('#cbd9df'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Камера запускается…')
            return
        painter.drawPixmap(image, self.frame, QRectF(self.frame.rect()))
        left, top, right, bottom = self.area
        selected = QRectF(self.pixel(left, top), self.pixel(right, bottom)).normalized()
        # Dim only the area outside the selected rectangle.
        painter.setClipRect(image)
        shade = QColor(0, 0, 0, 140)
        for rect in (QRectF(image.left(), image.top(), image.width(), selected.top() - image.top()),
                     QRectF(image.left(), selected.bottom(), image.width(), image.bottom() - selected.bottom()),
                     QRectF(image.left(), selected.top(), selected.left() - image.left(), selected.height()),
                     QRectF(selected.right(), selected.top(), image.right() - selected.right(), selected.height())):
            painter.fillRect(rect, shade)
        painter.setPen(QPen(QColor('#29e1e7'), 2))
        painter.drawRect(selected)
        painter.setBrush(QColor('#29e1e7'))
        for point in (selected.topLeft(), selected.topRight(), selected.bottomLeft(), selected.bottomRight()):
            painter.drawRect(QRectF(point.x() - 4, point.y() - 4, 8, 8))
        painter.setPen(QColor('#ffffff'))
        painter.drawText(selected.adjusted(12, 8, -12, -8), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter, 'ВЕРХ ЭКРАНА')
        painter.drawText(selected.adjusted(12, 8, -12, -8), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter, 'НИЗ ЭКРАНА')

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.image_rect().contains(event.position()):
            return
        point = event.position()
        l, t, r, b = self.area
        corner = next(((ix, iy) for ix, iy in ((0, 1), (2, 1), (0, 3), (2, 3))
                       if (self.pixel(self.area[ix], self.area[iy]) - point).manhattanLength() <= 18), None)
        start = self.normalized(point)
        if corner:
            self.drag = ('resize', start, list(self.area), corner)
        elif QRectF(self.pixel(l, t), self.pixel(r, b)).contains(point):
            self.drag = ('move', start, list(self.area), None)
        else:
            self.drag = ('draw', start, list(self.area), None)
            self.area = [start[0], start[1], start[0], start[1]]
        self.changed.emit(False)
        self.update()

    def mouseMoveEvent(self, event):
        if not self.drag:
            return
        mode, start, original, corner = self.drag
        x, y = self.normalized(event.position())
        if mode == 'move':
            l, t, r, b = original
            dx = max(-l, min(1 - r, x - start[0]))
            dy = max(-t, min(1 - b, y - start[1]))
            self.area = [l + dx, t + dy, r + dx, b + dy]
        elif mode == 'resize':
            self.area = list(original)
            self.area[corner[0]], self.area[corner[1]] = x, y
            l, t, r, b = self.area
            self.area = [min(l, r), min(t, b), max(l, r), max(t, b)]
        else:
            self.area = [min(start[0], x), min(start[1], y), max(start[0], x), max(start[1], y)]
        self.update()

    def mouseReleaseEvent(self, event):
        if self.drag:
            self.mouseMoveEvent(event)
            self.drag = None
            self.changed.emit(valid_area(self.area))


class AreaPicker(QDialog):
    def __init__(self, parent, controller, area):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle('Поле прямого наведения')
        self.resize(960, 700)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        title = QLabel('Выберите удобное поле для руки')
        title.setStyleSheet('font-size:24px;font-weight:600;')
        layout.addWidget(title)
        note = QLabel('Потяните за углы рамки или нарисуйте новую снаружи. Внутри рамку можно перемещать. '
                      'Её края станут краями выбранных экранов. Изображение зеркальное, как в обычном превью. '
                      'Управление жестами на время настройки приостановлено.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.canvas = AreaCanvas(area)
        layout.addWidget(self.canvas, 1)
        self.status = QLabel('Настройте рамку и нажмите «Сохранить поле».')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        reset = QPushButton('Стандартное поле')
        reset.clicked.connect(lambda: self.canvas.set_area(DEFAULT_AREA))
        buttons.addWidget(reset)
        full = QPushButton('Весь кадр')
        full.clicked.connect(lambda: self.canvas.set_area([0, 0, 1, 1]))
        buttons.addWidget(full)
        buttons.addStretch()
        cancel = QPushButton('Отмена')
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.confirm = QPushButton('Сохранить поле')
        self.confirm.setObjectName('SettingsDone')
        self.confirm.setEnabled(False)
        self.confirm.clicked.connect(self.accept)
        buttons.addWidget(self.confirm)
        layout.addLayout(buttons)
        self.canvas.changed.connect(self.selection_changed)
        controller.message.connect(self.receive)
        self.finished.connect(self.disconnect)
        if controller.frame:
            self.canvas.show_image(controller.frame)

    def selection_changed(self, valid):
        self.confirm.setEnabled(valid)
        if not valid and not self.canvas.frame.isNull():
            self.status.setText('Поле должно занимать хотя бы 10% ширины и высоты кадра.')
        elif valid:
            l, t, r, b = self.canvas.area
            self.status.setText(f'Лево {l:.0%} · верх {t:.0%} · право {r:.0%} · низ {b:.0%}')

    def disconnect(self):
        try:
            self.controller.message.disconnect(self.receive)
        except (TypeError, RuntimeError):
            pass

    def receive(self, data):
        if data.get('_epoch', self.controller.epoch) != self.controller.epoch:
            return
        if data.get('type') == 'preview':
            self.canvas.show_image(data.get('image'))
        elif data.get('type') in ('error', 'ended'):
            self.status.setText(data.get('text', 'Камера остановилась'))
            self.confirm.setEnabled(False)


def pick_pointer_area(panel):
    from core.room_gesture_rules import read_settings, save_settings
    from core.room_gesture_panel import DATA_DIR
    controller = panel.controller
    was_running = controller.camera_snapshot()['running']
    controller._pointer_setup = True
    controller.release_pointer()
    if hasattr(controller, 'release_game'):
        controller.release_game()
    controller._clear_drag()
    if controller.relay:
        controller.relay.invalidate()
    try:
        if not was_running:
            controller.start()
        path = DATA_DIR / 'config/gesture-actions.json'
        dialog = AreaPicker(panel, controller, read_settings(path)['mouse_area'])
        if dialog.exec() == QDialog.DialogCode.Accepted and valid_area(dialog.canvas.area):
            config = read_settings(path)
            config['mouse_area'] = list(dialog.canvas.area)
            save_settings(path, config)
            panel.bindings.update(mouse_area=config['mouse_area'])
            panel.update_pointer_area_summary()
    except Exception as error:
        QMessageBox.warning(panel, 'Поле прямого наведения', str(error))
    finally:
        try:
            controller.reload_rules()
            if not was_running:
                controller.stop()
        finally:
            controller._pointer_setup = False
