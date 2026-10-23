"""Select an ordinary pen's visible tip in the local camera preview."""
import base64
from PyQt6.QtCore import Qt,QRectF,pyqtSignal
from PyQt6.QtGui import QColor,QPainter,QPen,QPixmap
from PyQt6.QtWidgets import QDialog,QHBoxLayout,QLabel,QMessageBox,QPushButton,QVBoxLayout,QWidget


class ObjectCanvas(QWidget):
    selected=pyqtSignal(bool)
    def __init__(self):
        super().__init__();self.frame=QPixmap();self.start=None;self.end=None;self.dragging=False
        self.setMinimumSize(640,360);self.setMouseTracking(True)
        self.setAccessibleName('Выделите мышью видимый конец ручки на изображении камеры')
    def image_rect(self):
        if self.frame.isNull():return QRectF()
        scale=min(self.width()/self.frame.width(),self.height()/self.frame.height())
        w,h=self.frame.width()*scale,self.frame.height()*scale
        return QRectF((self.width()-w)/2,(self.height()-h)/2,w,h)
    def box(self):
        if self.start is None or self.end is None:return None
        image=self.image_rect();rect=QRectF(self.start,self.end).normalized().intersected(image)
        if image.isEmpty() or rect.width()/image.width()*640<10 or rect.height()/image.height()*360<10:return None
        if rect.width()*rect.height()>image.width()*image.height()*.4:return None
        return [(rect.x()-image.x())/image.width(),(rect.y()-image.y())/image.height(),rect.width()/image.width(),rect.height()/image.height()]
    def show_image(self,data):
        frame=QPixmap()
        try:
            if frame.loadFromData(base64.b64decode(data,validate=True)):self.frame=frame;self.update()
        except (TypeError,ValueError):pass
    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('#101517'))
        rect=self.image_rect()
        if self.frame.isNull():
            painter.setPen(QColor('#cbd9df'));painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'Камера запускается…');return
        painter.drawPixmap(rect,self.frame,QRectF(self.frame.rect()))
        if self.start is not None and self.end is not None:
            selected=QRectF(self.start,self.end).normalized().intersected(rect)
            painter.setPen(QPen(QColor('#29e1e7'),2));painter.setBrush(QColor(20,210,220,30));painter.drawRect(selected)
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.image_rect().contains(event.position()):
            self.start=event.position();self.end=self.start;self.dragging=True;self.selected.emit(False);self.update()
    def mouseMoveEvent(self,event):
        if self.dragging:self.end=event.position();self.update()
    def mouseReleaseEvent(self,event):
        if self.dragging:
            self.end=event.position();self.dragging=False;self.selected.emit(self.box() is not None);self.update()


class ObjectPicker(QDialog):
    def __init__(self,window):
        super().__init__(window);self.controller=window._gesture_controller
        self.setWindowTitle('Выбрать ручку · AirControl');self.resize(940,680)
        layout=QVBoxLayout(self);layout.setContentsMargins(22,22,22,22);layout.setSpacing(14)
        title=QLabel('Выделите видимый конец ручки');title.setStyleSheet('font-size:24px;font-weight:600;');layout.addWidget(title)
        text=QLabel('Держите ручку спокойно. Обведите мышью её верхнюю часть или колпачок, включая края. '
                    'Не выделяйте всю кисть или большой участок фона. После подтверждения будет 5 секунд, '
                    'чтобы переключиться в игру и поставить ручку в нейтральное положение.');text.setWordWrap(True);layout.addWidget(text)
        self.canvas=ObjectCanvas();layout.addWidget(self.canvas,1)
        self.status=QLabel('Узор или дополнительная метка не требуются. Видимый конец ручки должен отличаться от фона.');self.status.setWordWrap(True);layout.addWidget(self.status)
        buttons=QHBoxLayout();cancel=QPushButton('Отмена');cancel.clicked.connect(self.reject);buttons.addWidget(cancel);buttons.addStretch()
        self.confirm=QPushButton('Следить за этой ручкой');self.confirm.setObjectName('SettingsDone');self.confirm.setEnabled(False);self.confirm.clicked.connect(self.accept);buttons.addWidget(self.confirm);layout.addLayout(buttons)
        self.canvas.selected.connect(self.confirm.setEnabled);self.controller.message.connect(self.receive)
        self.finished.connect(self.disconnect)
        if self.controller.frame:self.canvas.show_image(self.controller.frame)
    def disconnect(self):
        try:self.controller.message.disconnect(self.receive)
        except (TypeError,RuntimeError):pass
    def receive(self,data):
        if data.get('type') in ('error','ended') and not self.controller.camera_snapshot()['running']:
            self.status.setText(self.controller.status);return
        if data.get('_epoch',self.controller.epoch)!=self.controller.epoch:return
        if data.get('type')=='preview':self.canvas.show_image(data.get('image'))
        elif data.get('type') in ('error','ended'):self.status.setText(data.get('text','Камера остановилась'))


def pick_object(window):
    controller=window._gesture_controller
    try:
        if not controller.camera_snapshot()['running']:controller.start()
        dialog=ObjectPicker(window)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            box=dialog.canvas.box()
            if box is not None:controller.select_object(box)
    except Exception as error:QMessageBox.warning(window,'Выбор ручки',str(error))
