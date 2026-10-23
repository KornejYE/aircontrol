"""Searchable settings navigation. Indexes labels, never entered field values."""
from dataclasses import dataclass
from PyQt6.QtCore import Qt,QTimer,QEvent
from PyQt6.QtGui import QKeySequence,QShortcut
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QListWidget,QListWidgetItem,QStackedWidget,QScrollArea,QFrame,QPushButton
from core.room_shell import BG,PANEL,EDGE,CYAN,TEXT,DIM


@dataclass
class Setting:
    title:str
    page:str
    keywords:str=''
    target:object=None
    action:object=None


class SettingsWorkspace(QWidget):
    def __init__(self,parent=None,placeholder='Найти настройку…'):
        super().__init__(parent)
        self.sections={};self.entries=[];self.current_key=None;self._opening=False
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(16)
        self.search=QLineEdit();self.search.setAccessibleName('Поиск настроек');self.search.setPlaceholderText(placeholder);self.search.setClearButtonEnabled(True);self.search.setMinimumHeight(44)
        self.search.installEventFilter(self);root.addWidget(self.search)
        body=QHBoxLayout();body.setSpacing(18)
        self.nav=QListWidget();self.nav.setAccessibleName('Разделы настроек');self.nav.setFixedWidth(194);self.nav.setSpacing(3);self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.nav.setWordWrap(True);self.nav.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.nav.setStyleSheet(f'QListWidget{{background:{PANEL};border:1px solid {EDGE};border-radius:12px;padding:8px;outline:0;}} QListWidget::item{{padding:13px 10px;color:{DIM};border-radius:8px;}} QListWidget::item:selected{{background:#293e40;color:{TEXT};}} QListWidget::item:hover{{background:#252d31;}}')
        body.addWidget(self.nav)
        self.stack=QStackedWidget();body.addWidget(self.stack,1);root.addLayout(body,1)
        self.results_page=QWidget();results_layout=QVBoxLayout(self.results_page);results_layout.setContentsMargins(0,0,0,0)
        self.result_title=QLabel();self.result_title.setWordWrap(True);self.result_title.setStyleSheet('font-size:23px;font-weight:600;');results_layout.addWidget(self.result_title)
        self.results=QListWidget();self.results.setAccessibleName('Результаты поиска настроек');self.results.setWordWrap(True);self.results.setSpacing(6)
        self.results.setStyleSheet(f'QListWidget{{background:transparent;border:0;outline:0;}} QListWidget::item{{background:{PANEL};border:1px solid {EDGE};border-radius:10px;padding:14px;color:{TEXT};}} QListWidget::item:selected{{border-color:{CYAN};background:#293e40;}}')
        results_layout.addWidget(self.results,1)
        self.empty=QLabel('Ничего не найдено. Попробуйте «скорость», «камера», «голос» или «свет».');self.empty.setWordWrap(True);self.empty.setStyleSheet(f'color:{DIM};font-size:16px;');results_layout.addWidget(self.empty)
        self.stack.addWidget(self.results_page)
        self.search.textChanged.connect(self.filter);self.search.returnPressed.connect(self.open_first)
        self.results.itemClicked.connect(self.open_result);self.results.itemActivated.connect(self.open_result)
        self.nav.currentRowChanged.connect(self._selected)
        self.find_shortcut=QShortcut(QKeySequence.StandardKey.Find,self);self.find_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);self.find_shortcut.activated.connect(self.focus_search)

    def eventFilter(self,watched,event):
        if watched is self.search and event.type()==QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):self.open_first();return True
            if event.key()==Qt.Key.Key_Escape and self.search.text():self.search.clear();return True
            if event.key()==Qt.Key.Key_Down and self.results.count() and self.search.text():self.results.setFocus();self.results.setCurrentRow(0);return True
        return super().eventFilter(watched,event)

    def focus_search(self):self.search.setFocus();self.search.selectAll()

    def add_page(self,key,title,description,widgets=()):
        frame=QFrame();frame.setObjectName('SettingsPage');outer=QVBoxLayout(frame);outer.setContentsMargins(22,20,18,12);outer.setSpacing(12)
        heading=QLabel(title);heading.setStyleSheet('font-size:25px;font-weight:600;');outer.addWidget(heading)
        note=QLabel(description);note.setWordWrap(True);note.setStyleSheet(f'color:{DIM};font-size:16px;');outer.addWidget(note)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);scroll.setAccessibleName(title+' · параметры')
        content=QWidget();content.setObjectName('SettingsBody');layout=QVBoxLayout(content);layout.setContentsMargins(0,5,8,12);layout.setSpacing(16);scroll.setWidget(content);outer.addWidget(scroll,1)
        for widget in widgets:
            if widget is not None:layout.addWidget(widget);widget.show()
        layout.addStretch()
        self.sections[key]=dict(title=title,frame=frame,layout=layout,scroll=scroll)
        item=QListWidgetItem(title);item.setData(Qt.ItemDataRole.UserRole,key);self.nav.addItem(item);self.stack.addWidget(frame)
        if self.current_key is None:self.select(key)
        return layout

    def add(self,key,widget):
        layout=self.sections[key]['layout'];layout.insertWidget(layout.count()-1,widget);widget.show()

    def register(self,title,page,keywords='',target=None,action=None):
        entry=Setting(title,page,keywords,target,action);self.entries.append(entry);return entry

    def _selected(self,row):
        if not self._opening and row>=0:self.select(self.nav.item(row).data(Qt.ItemDataRole.UserRole))

    def select(self,key,target=None):
        if key not in self.sections:return
        self._opening=True
        try:
            self.search.clear();self.current_key=key;self.stack.setCurrentWidget(self.sections[key]['frame'])
            self.nav.setCurrentRow(list(self.sections).index(key))
        finally:self._opening=False
        if target is not None:
            def reveal():
                if not target.isVisible():return
                self.sections[key]['scroll'].ensureWidgetVisible(target,15,30)
                target.setFocus(Qt.FocusReason.ShortcutFocusReason)
                target.setProperty('settingsHighlight',True);target.style().unpolish(target);target.style().polish(target)
                def clear():
                    try:target.setProperty('settingsHighlight',False);target.style().unpolish(target);target.style().polish(target)
                    except RuntimeError:pass
                QTimer.singleShot(1800,clear)
            QTimer.singleShot(0,reveal)

    def filter(self,value):
        if self._opening:return
        terms=value.casefold().replace('ё','е').split()
        if not terms:
            if self.current_key:self.stack.setCurrentWidget(self.sections[self.current_key]['frame'])
            return
        self.results.clear();matches=[]
        for index,entry in enumerate(self.entries):
            title=self.sections[entry.page]['title'];keywords=entry.keywords() if callable(entry.keywords) else entry.keywords
            haystack=(entry.title+' '+title+' '+keywords).casefold().replace('ё','е')
            if not all(term in haystack for term in terms):continue
            caption=entry.title.casefold().replace('ё','е')
            score=sum(4 if term in caption else 1 for term in terms)+(6 if ' '.join(terms) in caption else 0)
            matches.append((-score,index,entry,title))
        for _,index,entry,title in sorted(matches,key=lambda row:(row[0],row[1])):
            item=QListWidgetItem(entry.title+'\n'+title+'  →');item.setData(Qt.ItemDataRole.UserRole,index);self.results.addItem(item)
        self.result_title.setText('Найдено настроек: '+str(self.results.count()));self.empty.setVisible(not self.results.count());self.stack.setCurrentWidget(self.results_page)
        if self.results.count():self.results.setCurrentRow(0)

    def open_first(self):
        if self.search.text() and self.results.count():self.open_result(self.results.currentItem() or self.results.item(0))

    def open_result(self,item):
        entry=self.entries[item.data(Qt.ItemDataRole.UserRole)];self.select(entry.page,entry.target)
        if entry.action:entry.action()


def card(title,description=''):
    frame=QFrame();frame.setObjectName('SettingsCard');box=QVBoxLayout(frame);box.setContentsMargins(20,18,20,20);box.setSpacing(12)
    label=QLabel(title);label.setWordWrap(True);label.setStyleSheet('font-size:19px;font-weight:600;');box.addWidget(label)
    if description:
        note=QLabel(description);note.setWordWrap(True);note.setStyleSheet(f'color:{DIM};font-size:16px;');box.addWidget(note)
    return frame,box
