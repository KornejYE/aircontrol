"""User-selected object tracking, in memory only. No object recognition model.

The selected cap/tip follows CSRT appearance tracking. Input stops on loss,
appearance mismatch or stale frames; no automatic search for a replacement.
This tracks image displacement, not an arbitrary pen's metric 3D pose.
"""
import math


def valid_box(box):
    return (isinstance(box,(list,tuple)) and len(box)==4
            and all(type(v) in (int,float) and math.isfinite(v) for v in box)
            and 0<=box[0]<1 and 0<=box[1]<1 and .015<=box[2]<=.9 and .015<=box[3]<=.9
            and box[0]+box[2]<=1+1e-9 and box[1]+box[3]<=1+1e-9 and box[2]*box[3]<.4)


class ObjectJoystick:
    def __init__(self, tracker_factory=None):
        self.factory=tracker_factory
        self.clear()

    def clear(self):
        self.selection=None;self.tracker=None;self.bbox=None;self.histogram=None
        self.ready_at=None;self.neutral=None;self.xy=(0.,0.);self.last=None
        self.state='idle';self.feedback='Выделите видимый конец ручки кнопкой «Выбрать ручку»'

    def select(self,box,now,delay=5.):
        if not valid_box(box):raise ValueError('Выделите небольшой прямоугольник вокруг конца ручки')
        self.clear();self.selection=tuple(box);self.recenter(now,delay)

    def recenter(self,now,delay=5.):
        if self.selection is None:raise ValueError('Сначала выберите ручку на изображении камеры')
        self.ready_at=now+max(.5,min(10.,delay));self.neutral=None;self.xy=(0.,0.)
        self.state='arming'

    def pause(self):
        self.ready_at=None;self.neutral=None;self.xy=(0.,0.);self.state='idle'
        self.feedback='Джойстик остановлен · нажмите «Новая нейтраль» для продолжения'

    def lose(self,text):
        self.tracker=None;self.selection=None;self.ready_at=None;self.neutral=None
        self.xy=(0.,0.);self.state='lost';self.feedback=text

    @staticmethod
    def _hist(frame,box):
        import cv2
        x,y,w,h=map(round,box);crop=frame[y:y+h,x:x+w]
        if not crop.size:raise ValueError('Объект вне кадра')
        hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
        histogram=cv2.calcHist([hsv],[0,1,2],None,[8,8,8],[0,180,0,256,0,256])
        return cv2.normalize(histogram,None,alpha=1.,norm_type=cv2.NORM_L1)

    def update(self,frame,now,config):
        import cv2
        from core.room_hand_joystick import game_settings
        config=game_settings(config)
        dt=min(.08,now-self.last) if self.last is not None else 1/30
        if self.selection is not None and self.last is not None and not 0<now-self.last<=.3:
            self.lose('Камера задержалась · выберите ручку заново')
        self.last=now
        if self.selection is not None:
            height,width=frame.shape[:2]
            try:
                if self.tracker is None:
                    x,y,w,h=self.selection;box=(round(x*width),round(y*height),round(w*width),round(h*height))
                    box=(box[0],box[1],min(box[2],width-box[0]),min(box[3],height-box[1]))
                    if min(box[2:])<10:raise ValueError('Выделите конец ручки чуть крупнее, вместе с краями')
                    crop=frame[box[1]:box[1]+box[3],box[0]:box[0]+box[2]]
                    if cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY).std()<7:
                        raise ValueError('В выделении нет различимых деталей · захватите края ручки')
                    if self.factory:self.tracker=self.factory()
                    else:
                        parameters=cv2.TrackerCSRT_Params();parameters.psr_threshold=.08
                        parameters.template_size=160.;parameters.number_of_scales=17
                        self.tracker=cv2.TrackerCSRT_create(parameters)
                    result=self.tracker.init(frame,box)
                    if result is False:raise ValueError('Не удалось запомнить выбранный предмет')
                    self.bbox=box;self.histogram=self._hist(frame,box)
                else:
                    ok,box=self.tracker.update(frame)
                    if not ok:raise ValueError('Ручка потеряна · выберите её заново')
                    x,y,w,h=box
                    if (not all(math.isfinite(v) for v in box) or min(w,h)<8
                            or x<0 or y<0 or x+w>width or y+h>height):
                        raise ValueError('Ручка вышла из кадра · выберите её заново')
                    previous=self.bbox
                    movement=math.hypot(x+w/2-previous[0]-previous[2]/2,y+h/2-previous[1]-previous[3]/2)
                    if movement>height*.3 or not .4<w*h/(previous[2]*previous[3])<2.5:
                        raise ValueError('Потеряна непрерывность движения · выберите ручку заново')
                    if cv2.compareHist(self.histogram,self._hist(frame,box),cv2.HISTCMP_BHATTACHARYYA)>.65:
                        raise ValueError('Внешний вид предмета изменился · выберите ручку заново')
                    self.bbox=box
                x,y,w,h=self.bbox;center=((x+w/2)/height,(y+h/2)/height)
                if self.ready_at is not None:
                    if now<self.ready_at:
                        self.state='arming';self.feedback=f'Нейтраль через {max(1,math.ceil(self.ready_at-now))} с · переключитесь в игру и держите ручку спокойно'
                    else:
                        if self.neutral is None:self.neutral=center
                        raw=tuple((p-n)/config['object_span'] for p,n in zip(center,self.neutral))
                        length=math.hypot(*raw)
                        scale=max(0.,min(1.,(length-config['deadzone'])/(1-config['deadzone'])))**1.15/length if length else 0.
                        desired=(raw[0]*scale,raw[1]*scale*(-1 if config['invert_y'] else 1))
                        alpha=1-math.exp(-max(.001,dt)/.035)
                        self.xy=tuple(a+(b-a)*alpha for a,b in zip(self.xy,desired))
                        self.state='active';self.feedback='Ручка отслеживается · двигайте её конец в кадре · Esc останавливает'
            except (ValueError,cv2.error) as error:self.lose(str(error))
        active=self.state=='active'
        return dict(action='joystick',phase='update' if active or self.state=='arming' else 'cancel',
                    x=round(self.xy[0],4) if active else 0.,y=round(self.xy[1],4) if active else 0.,
                    active=active,state=self.state)

    def draw(self,frame):
        import cv2
        if self.bbox is None:return
        x,y,w,h=map(round,self.bbox)
        colour=(210,210,30) if self.state=='active' else (80,150,230) if self.state=='arming' else (80,80,220)
        cv2.rectangle(frame,(x,y),(x+w,y+h),colour,2)
        cv2.drawMarker(frame,(x+w//2,y+h//2),colour,cv2.MARKER_CROSS,16,2)
        cv2.putText(frame,'OBJECT',(x,max(20,y-8)),cv2.FONT_HERSHEY_SIMPLEX,.6,colour,2,cv2.LINE_AA)
