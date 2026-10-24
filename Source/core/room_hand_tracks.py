"""Track visible hands; route only the largest anatomical right and left palm."""
from dataclasses import dataclass
import math

MAX_HANDS = 8
CONNECTIONS = tuple((a, b) for chain in ((0,1,2,3,4), (0,5,6,7,8),
                    (5,9,10,11,12), (9,13,14,15,16), (13,17,18,19,20), (0,17))
                    for a,b in zip(chain, chain[1:]))
PALM = (0, 5, 9, 13, 17)

@dataclass
class VisibleHand:
    identity: int
    side: str
    landmarks: object
    size: float
    active: bool = False

class HandTracks:
    def __init__(self):
        self.tracks = {}
        self.visible = []
        self.selected_ids = {}
        self.changed = set()
        self._sequence = 0
        self._side_locks = {}

    def lock_side(self, side):
        """Keep the established anatomical label of the selected physical hand.

        This does not lock ownership: a larger visible hand can still take over
        selection and trigger changed/reset. Call only after pointer arming.
        """
        if side not in ('Right','Left'):
            return False
        identity = self.selected_ids.get(side)
        track = self.tracks.get(identity)
        if track is None or track['side'] != side:
            return False
        if not any(h.identity == identity for h in self.visible):
            return False
        if self._side_locks.get(identity) == side:
            return True
        self._side_locks[identity] = side
        track['conflict'] = None
        return True

    def clear_locks(self):
        for identity in self._side_locks:
            if identity in self.tracks:
                self.tracks[identity]['conflict'] = None
        self._side_locks.clear()

    def update(self, detections, now):
        """Keep all detections, including several real hands of the same side.

        Size uses palm length × width, unaffected by opening the fingers. It is
        a projected-size proxy for proximity, not a metric depth measurement.
        Positions, size and persistent IDs bridge detector ordering/label jitter.
        """
        rows = []
        for points, label, confidence in detections[:MAX_HANDS]:
            try:
                xy = [(float(p.x), float(p.y)) if hasattr(p, 'x') else
                      (float(p[0]), float(p[1])) for p in points]
                if len(xy) != 21 or label not in ('Right','Left') or not all(math.isfinite(v) for p in xy for v in p):
                    continue
                centre = tuple(sum(xy[i][a] for i in PALM)/len(PALM) for a in (0,1))
                size = math.dist(xy[0],xy[9])*math.dist(xy[5],xy[17])
                if size < 1e-8: continue
                rows.append((points,label,max(0.,min(1.,float(confidence))),centre,size))
            except (AttributeError,IndexError,TypeError,ValueError,OverflowError):
                continue
        self.tracks = {i:t for i,t in self.tracks.items() if 0 <= now-t['at'] < .45}
        self._side_locks = {i:side for i,side in self._side_locks.items() if i in self.tracks}
        previous_visible = {h.identity for h in self.visible}
        pairs = []
        for index, (_,label,confidence,centre,size) in enumerate(rows):
            for identity, track in self.tracks.items():
                # A different hand entering the same spot must not inherit a
                # disappeared hand's side lock. Keep short same-side recovery.
                if identity not in previous_visible and label != track['side'] and confidence >= .85:
                    continue
                distance = math.dist(centre, track['centre'])
                ratio = size/track['size']
                if distance > max(.12,min(.30,math.sqrt(track['size'])*1.5)) or not .3 < ratio < 3.3:
                    continue
                cost = distance/.20 + abs(math.log(ratio))*.35
                if label != track['side']: cost += confidence*.4
                pairs.append((cost,identity,index))
        assigned = {}; used = set()
        for _, identity, index in sorted(pairs):
            if index not in assigned and identity not in used:
                assigned[index]=identity;used.add(identity)
        visible = []
        for index,(points,label,confidence,centre,size) in enumerate(rows):
            identity = assigned.get(index)
            if identity is None:
                self._sequence += 1; identity = self._sequence
                track = {'side':label, 'conflict':None}
            else:
                track = self.tracks[identity]
                if identity in self._side_locks:
                    track['side'] = self._side_locks[identity]
                    # A lock absorbs brief label jitter, not a permanent model
                    # mistake. Repeated locking each frame must not reset this.
                    if label == track['side'] or confidence < .85:
                        track['conflict'] = None
                    elif track['conflict'] is None:
                        track['conflict'] = now
                    elif now-track['conflict'] >= 1.:
                        track['side'] = label
                        track['conflict'] = None
                        self._side_locks.pop(identity, None)
                elif label == track['side'] or confidence < .85:
                    track['conflict'] = None
                elif track['conflict'] is None:
                    track['conflict'] = now
                elif now-track['conflict'] >= .25:
                    track['side']=label;track['conflict']=None
            track.update(centre=centre,size=size,at=now)
            self.tracks[identity]=track
            visible.append(VisibleHand(identity,track['side'],points,size))
        visible_ids = {h.identity for h in visible}
        self._side_locks = {i:side for i,side in self._side_locks.items() if i in visible_ids}
        self.changed = set()
        selected = []
        for side in ('Right','Left'):
            candidates = [h for h in visible if h.side == side]
            if not candidates: continue
            winner = max(candidates,key=lambda h:(h.size,-h.identity))
            previous = next((h for h in candidates if h.identity==self.selected_ids.get(side)),None)
            # A tiny apparent-size fluctuation should not alternate two owners.
            if previous and previous.size >= winner.size*.97: winner=previous
            old = self.selected_ids.get(side)
            if old is not None and old != winner.identity: self.changed.add(side)
            self.selected_ids[side]=winner.identity
            winner.active=True;selected.append((side,winner.landmarks))
        self.visible = visible
        return selected
