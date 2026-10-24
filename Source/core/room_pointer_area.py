"""Normalized camera work area for absolute hand pointing."""
import math

DEFAULT_AREA = (.15, .15, .85, .85)
MIN_SPAN = .10


def valid_area(value):
    return (isinstance(value, (list, tuple)) and len(value) == 4
            and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in value)
            and value[2] - value[0] >= MIN_SPAN - 1e-9
            and value[3] - value[1] >= MIN_SPAN - 1e-9)


def pointer_area(value=None):
    return list(value) if valid_area(value) else list(DEFAULT_AREA)


def map_point(point, area):
    left, top, right, bottom = pointer_area(area)
    return [max(0., min(1., (point[0] - left) / (right - left))),
            max(0., min(1., (point[1] - top) / (bottom - top)))]


def display_target(value):
    if value in ('all', 'current'):
        return value
    if isinstance(value, str) and value.startswith('display:') and value[8:].isascii() and value[8:].isdigit() and len(value) < 24 and 0 < int(value[8:]) <= 0xffffffff:
        return 'display:' + str(int(value[8:]))
    if isinstance(value, str) and value.startswith('displays:') and len(value) < 400:
        parts = value[9:].split(',')
        if 1 <= len(parts) <= 32 and all(p.isascii() and p.isdigit() and 0 < int(p) <= 0xffffffff for p in parts):
            return 'displays:' + ','.join(str(i) for i in sorted({int(p) for p in parts}))
    return 'all'


def selected_display_ids(value):
    value = display_target(value)
    if value.startswith('display:'):
        return {int(value[8:])}
    if value.startswith('displays:'):
        return {int(p) for p in value[9:].split(',')}
    return set()


def absolute_desktop_point(xy, rectangles):
    """Map across the configured virtual desktop, including negative origins.

    The caller projects gap/offset corners onto an actual monitor afterwards.
    """
    left = min(r.origin.x for r in rectangles)
    top = min(r.origin.y for r in rectangles)
    right = max(r.origin.x + r.size.width for r in rectangles)
    bottom = max(r.origin.y + r.size.height for r in rectangles)
    return left + xy[0] * (right - left - 1), top + xy[1] * (bottom - top - 1)


def display_options():
    """Read geometry only; never request permission or post input."""
    try:
        import sys
        if sys.platform == 'win32':
            from core.room_windows_input import WindowsAPI
            values = WindowsAPI().displays()
        elif sys.platform == 'darwin':
            import Quartz as q
            _, ids, _ = q.CGGetActiveDisplayList(32, None, None)
            values = [(identifier, q.CGDisplayBounds(identifier)) for identifier in ids]
        else:
            return []
        values.sort(key=lambda item: (item[1].origin.x, item[1].origin.y))
        return [(f'display:{identifier}', f'Экран {index + 1} · {int(r.size.width)} × {int(r.size.height)}',
                 (r.origin.x, r.origin.y, r.size.width, r.size.height))
                for index, (identifier, r) in enumerate(values)]
    except (ImportError, OSError, RuntimeError):
        return []
