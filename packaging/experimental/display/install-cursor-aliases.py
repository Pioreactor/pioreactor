#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Supply CSS cursor names expected by WPE in Debian's DMZ-White theme."""
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/pioreactor-display/rootfs")
cursors = root / "usr/share/icons/DMZ-White/cursors"
aliases = {
    "default": "left_ptr",
    "pointer": "hand2",
    "text": "xterm",
    "wait": "watch",
    "progress": "left_ptr_watch",
    "help": "left_ptr_help",
    "e-resize": "right_side",
    "w-resize": "left_side",
    "n-resize": "top_side",
    "s-resize": "bottom_side",
    "ne-resize": "top_right_corner",
    "nw-resize": "top_left_corner",
    "se-resize": "bottom_right_corner",
    "sw-resize": "bottom_left_corner",
    "ew-resize": "sb_h_double_arrow",
    "ns-resize": "sb_v_double_arrow",
    "nesw-resize": "fd_double_arrow",
    "nwse-resize": "bd_double_arrow",
    "col-resize": "sb_h_double_arrow",
    "row-resize": "sb_v_double_arrow",
    "not-allowed": "crossed_circle",
    "no-drop": "crossed_circle",
    "all-scroll": "fleur",
    "grab": "hand1",
    "context-menu": "left_ptr",
    "vertical-text": "xterm",
    "alias": "dnd-link",
}
for name, target in aliases.items():
    path = cursors / name
    if not (cursors / target).is_file():
        raise SystemExit(f"Missing cursor image: {target}; install dmz-cursor-theme first")
    if not path.exists() and not path.is_symlink():
        path.symlink_to(target)
print("WPE cursor aliases verified")
