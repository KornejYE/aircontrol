"""Shared visual constants for the gesture-only application."""
BG = '#141719'
PANEL = '#1b2023'
EDGE = '#323b40'
CYAN = '#63d5cf'
TEXT = '#eef2f3'
DIM = '#a3afb5'
BUTTON = f'''
QPushButton {{ background:#252d31; color:{TEXT}; border:1px solid {EDGE};
    border-radius:9px; padding:9px 14px; font:15px Arial; }}
QPushButton:hover {{ background:#303b40; border-color:#6b858b; }}
QPushButton:pressed {{ background:#35474c; }}
QPushButton:focus {{ border-color:{CYAN}; }}
QPushButton:disabled {{ background:#202629; color:#75838a; border-color:#30383c; }}
'''
