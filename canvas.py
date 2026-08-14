# canvas.py

from __future__ import annotations

import json
import threading
from pathlib import Path

from PyQt6.QtCore import (
    Qt,
    pyqtSignal,
    QPoint,
    QTimer,
)
from PyQt6.QtGui import (
    QColor,
    QPainter,
    QPen,
    QPixmap,
    QFont,
    QPolygon,
    QFontMetrics,
)
from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QScrollArea,
    QLabel,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QSlider,
    QSizePolicy,
    QTextEdit,
)

from config import (
    BASE_DIR,
    SAVED_OUTPUTS_DIR,
    CANVAS_W,
    CANVAS_H,
)

from utils import (
    qmsg_info,
    qmsg_warn,
    qmsg_err,
    qmsg_ask,
)


# ──────────────────────────────────────────────────────────────────────────────
# SHAPE CATALOG
# ──────────────────────────────────────────────────────────────────────────────

SHAPE_CATALOG = {
    "ER Diagram": [
        ("Entity",       "▭",  "er_entity"),
        ("Weak Entity",  "▣",  "er_weak_entity"),
        ("Attribute",    "◯",  "er_attribute"),
        ("Key Attr.",    "◎",  "er_key_attr"),
        ("Multi Attr.",  "◎",  "er_multi_attr"),
        ("Relationship", "◇",  "er_relationship"),
        ("Weak Rel.",    "◈",  "er_weak_relation"),
        ("Line",         "╱",  "line"),
        ("Arrow",        "→",  "arrow"),
        ("Dbl Arrow",    "↔",  "double_arrow"),
    ],

    "UML Diagram": [
        ("Class",        "⊡",  "uml_class"),
        ("Interface",    "⊟",  "uml_interface"),
        ("Package",      "⊞",  "uml_package"),
        ("Actor",        "☺",  "uml_actor"),
        ("Use Case",     "⬭",  "oval"),
        ("Component",    "⊠",  "uml_component"),
        ("Note",         "🗒", "uml_note"),
        ("Assoc.",       "→",  "arrow"),
        ("Depend.",      "⇢",  "dotted_arrow"),
        ("Inherit.",     "△",  "uml_inherit"),
        ("Aggreg.",      "◇",  "diamond"),
    ],

    "Flowchart": [
        ("Process",      "▭",  "rectangle"),
        ("Decision",     "◇",  "diamond"),
        ("Terminal",     "⬭",  "oval"),
        ("Document",     "⌵",  "flow_document"),
        ("Data I/O",     "▱",  "flow_parallelogram"),
        ("Connector",    "◯",  "flow_circle"),
        ("Database",     "⌭",  "flow_cylinder"),
        ("Delay",        "⊏",  "flow_delay"),
        ("Arrow",        "→",  "arrow"),
        ("Dotted Arr.",  "⇢",  "dotted_arrow"),
        ("Both Arr.",    "↔",  "double_arrow"),
        ("Line",         "╱",  "line"),
    ],
}


CANVAS_COLORS = [
    ("#111111", "Black"),
    ("#00c853", "Green"),
    ("#f44336", "Red"),
    ("#2196f3", "Blue"),
]


# ──────────────────────────────────────────────────────────────────────────────
# DRAWING CANVAS
# ──────────────────────────────────────────────────────────────────────────────

class DrawingCanvas(QWidget):
    """
    Large PyQt6 drawing canvas.

    Supports:
        - freehand drawing
        - text
        - ER / UML / Flowchart shapes
        - shape preview
        - undo
        - clear
        - scrolling
        - object selection
        - bounding box + handles
        - dragging
        - hit testing
        - double-click text editing
        - delete selected object
        - PNG saving
    """

    shape_mode_ended = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMinimumSize(800, 500)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.setFocusPolicy(
            Qt.FocusPolicy.StrongFocus
        )
        self.setCursor(
            Qt.CursorShape.CrossCursor
        )

        # ──────────────────────────────────────────────────────────────
        # Canvas
        # ──────────────────────────────────────────────────────────────

        self._pixmap = QPixmap(
            CANVAS_W,
            CANVAS_H,
        )
        self._pixmap.fill(
            QColor("#ffffff")
        )

        # ──────────────────────────────────────────────────────────────
        # Drawing settings
        # ──────────────────────────────────────────────────────────────

        self._brush_color = QColor(
            "#111111"
        )

        self._brush_size = 3
        self._font_size = 20

        self._shape_mode = None
        self._text_mode = False

        # ──────────────────────────────────────────────────────────────
        # Freehand state
        # ──────────────────────────────────────────────────────────────

        self._drawing = False
        self._current_stroke = None

        # ──────────────────────────────────────────────────────────────
        # Shape state
        # ──────────────────────────────────────────────────────────────

        self._shape_start = None
        self._preview_pixmap = None

        # ──────────────────────────────────────────────────────────────
        # Text state
        # ──────────────────────────────────────────────────────────────

        self._text_input = ""
        self._text_pos = None
        self._text_active = False
        self._active_text_id = None
        self._cursor_visible = True

        self._text_cursor_timer = QTimer(self)
        self._text_cursor_timer.setInterval(500)
        self._text_cursor_timer.timeout.connect(
            self._blink_text_cursor
        )

        # ──────────────────────────────────────────────────────────────
        # Object model
        # ──────────────────────────────────────────────────────────────

        self._objects = []
        self._next_object_id = 1

        # ──────────────────────────────────────────────────────────────
        # Selection
        # ──────────────────────────────────────────────────────────────

        self._selected_object_ids = []

        # ──────────────────────────────────────────────────────────────
        # Dragging
        # ──────────────────────────────────────────────────────────────

        self._dragging_object = False
        self._drag_last_pos = None

        # ──────────────────────────────────────────────────────────────
        # Undo
        # ──────────────────────────────────────────────────────────────

        self._undo_stack = []
        self._max_undo = 60

        # ──────────────────────────────────────────────────────────────
        # Scrolling
        # ──────────────────────────────────────────────────────────────

        self._scroll_x = 0
        self._scroll_y = 0

    # =========================================================================
    # SETTINGS
    # =========================================================================

    def set_color(self, hex_color: str):
        self._brush_color = QColor(
            hex_color
        )

    def set_brush_size(self, size: int):
        self._brush_size = max(
            1,
            int(size),
        )

    def set_font_size(self, size: int):
        self._font_size = max(
            8,
            int(size),
        )

    def set_shape_mode(self, mode: str | None):
        self._commit_text()

        self._shape_mode = mode
        self._text_mode = False

        self._deselect_objects()

        self.setCursor(
            Qt.CursorShape.CrossCursor
        )

    def set_text_mode(self, on: bool):
        self._commit_text()

        self._text_mode = bool(on)
        self._shape_mode = None

        self._deselect_objects()

        if on:
            self.setCursor(
                Qt.CursorShape.IBeamCursor
            )
        else:
            self.setCursor(
                Qt.CursorShape.CrossCursor
            )

    # =========================================================================
    # OBJECT IDS
    # =========================================================================

    def _new_object_id(self):
        object_id = self._next_object_id
        self._next_object_id += 1
        return object_id

    def _get_object(self, object_id):
        for obj in self._objects:
            if obj["id"] == object_id:
                return obj
        return None

    # =========================================================================
    # UNDO
    # =========================================================================

    def _save_undo(self):
        import copy

        self._undo_stack.append(
            {
                "objects": copy.deepcopy(
                    self._objects
                ),
                "next_id": self._next_object_id,
            }
        )

        if len(self._undo_stack) > self._max_undo:
            self._undo_stack.pop(0)

    def undo(self):
        if not self._undo_stack:
            return

        import copy

        snapshot = self._undo_stack.pop()

        self._objects = copy.deepcopy(
            snapshot["objects"]
        )

        self._next_object_id = (
            snapshot["next_id"]
        )

        self._selected_object_ids = []
        self._active_text_id = None
        self._text_active = False
        self._text_input = ""
        self._text_pos = None

        self._text_cursor_timer.stop()

        self._redraw()
        self.update()

    # =========================================================================
    # CLEAR
    # =========================================================================

    def clear_canvas(self):
        if self._objects:
            self._save_undo()

        self._objects.clear()
        self._selected_object_ids.clear()

        self._active_text_id = None
        self._text_active = False
        self._text_input = ""
        self._text_pos = None

        self._text_cursor_timer.stop()

        self._redraw()
        self.update()

    # =========================================================================
    # COORDINATES
    # =========================================================================

    def _canvas_pt(self, pos: QPoint) -> QPoint:
        return QPoint(
            pos.x() + self._scroll_x,
            pos.y() + self._scroll_y,
        )

    # =========================================================================
    # SELECTION
    # =========================================================================

    def _deselect_objects(self):
        self._selected_object_ids = []
        self.update()

    def _select_object(self, object_id):
        if object_id is None:
            self._deselect_objects()
            return

        self._selected_object_ids = [
            object_id
        ]

        self.update()

    def _bbox_of_objects(self, object_ids=None):
        if object_ids is None:
            object_ids = (
                self._selected_object_ids
            )

        boxes = []

        for object_id in object_ids:
            obj = self._get_object(
                object_id
            )

            if obj is None:
                continue

            bbox = self._object_bbox(
                obj
            )

            if bbox:
                boxes.append(bbox)

        if not boxes:
            return (
                0,
                0,
                0,
                0,
            )

        return (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )

    # =========================================================================
    # OBJECT BOUNDING BOX
    # =========================================================================

    def _object_bbox(self, obj):

        # ──────────────────────────────────────────────────────────────
        # Shape
        # ──────────────────────────────────────────────────────────────

        if obj["type"] == "shape":

            return (
                min(
                    obj["x1"],
                    obj["x2"],
                ),
                min(
                    obj["y1"],
                    obj["y2"],
                ),
                max(
                    obj["x1"],
                    obj["x2"],
                ),
                max(
                    obj["y1"],
                    obj["y2"],
                ),
            )

        # ──────────────────────────────────────────────────────────────
        # Text
        # ──────────────────────────────────────────────────────────────

        if obj["type"] == "text":

            font = QFont(
                "Arial",
                obj["font_size"],
            )

            metrics = QFontMetrics(
                font
            )

            lines = obj["text"].split(
                "\n"
            )

            width = 0

            for line in lines:
                width = max(
                    width,
                    metrics.horizontalAdvance(
                        line
                    ),
                )

            height = (
                metrics.lineSpacing()
                * max(
                    1,
                    len(lines),
                )
            )

            return (
                obj["x"],
                obj["y"] - metrics.ascent(),
                obj["x"] + width,
                obj["y"] - metrics.ascent() + height,
            )

        # ──────────────────────────────────────────────────────────────
        # Stroke
        # ──────────────────────────────────────────────────────────────

        if obj["type"] == "stroke":

            points = obj["points"]

            if not points:
                return None

            xs = [
                p[0]
                for p in points
            ]

            ys = [
                p[1]
                for p in points
            ]

            pad = max(
                4,
                obj["width"],
            )

            return (
                min(xs) - pad,
                min(ys) - pad,
                max(xs) + pad,
                max(ys) + pad,
            )

        return None

    # =========================================================================
    # HIT TESTING
    # =========================================================================

    def _find_object_at(
        self,
        x,
        y,
    ):
        # Topmost object first.
        for obj in reversed(
            self._objects
        ):

            bbox = self._object_bbox(
                obj
            )

            if not bbox:
                continue

            x1, y1, x2, y2 = bbox

            pad = 6

            if (
                x1 - pad <= x <= x2 + pad
                and
                y1 - pad <= y <= y2 + pad
            ):
                return obj["id"]

        return None

    def _find_text_at(
        self,
        x,
        y,
    ):

        for obj in reversed(
            self._objects
        ):

            if obj["type"] != "text":
                continue

            bbox = self._object_bbox(
                obj
            )

            if not bbox:
                continue

            x1, y1, x2, y2 = bbox

            if (
                x1 - 5 <= x <= x2 + 5
                and
                y1 - 5 <= y <= y2 + 5
            ):
                return obj["id"]

        return None

    # =========================================================================
    # MOVE OBJECTS
    # =========================================================================

    def _move_selected(
        self,
        dx,
        dy,
    ):

        if not self._selected_object_ids:
            return

        for object_id in (
            self._selected_object_ids
        ):

            obj = self._get_object(
                object_id
            )

            if obj is None:
                continue

            if obj["type"] == "shape":

                obj["x1"] += dx
                obj["y1"] += dy
                obj["x2"] += dx
                obj["y2"] += dy

            elif obj["type"] == "text":

                obj["x"] += dx
                obj["y"] += dy

            elif obj["type"] == "stroke":

                obj["points"] = [
                    (
                        x + dx,
                        y + dy,
                    )
                    for x, y in obj["points"]
                ]

        self._redraw()
        self.update()

    # =========================================================================
    # TEXT
    # =========================================================================

    def _create_text_cursor(
        self,
        x,
        y,
    ):

        self._commit_text()

        self._save_undo()

        object_id = (
            self._new_object_id()
        )

        obj = {
            "id": object_id,
            "type": "text",
            "x": x,
            "y": y,
            "text": "",
            "color": self._brush_color.name(),
            "font_size": self._font_size,
        }

        self._objects.append(
            obj
        )

        self._active_text_id = (
            object_id
        )

        self._text_active = True
        self._text_input = ""
        self._text_pos = QPoint(
            x,
            y,
        )

        self._cursor_visible = True

        self._text_cursor_timer.start()

        self._deselect_objects()

        self.setFocus()
        self.update()

    def _reopen_text(
        self,
        object_id,
    ):

        obj = self._get_object(
            object_id
        )

        if (
            not obj
            or obj["type"] != "text"
        ):
            return

        self._save_undo()

        self._active_text_id = (
            object_id
        )

        self._text_active = True

        self._text_input = obj["text"]

        self._text_pos = QPoint(
            obj["x"],
            obj["y"],
        )

        self._cursor_visible = True

        self._text_cursor_timer.start()

        self._deselect_objects()

        self.setFocus()
        self.update()

    def _commit_text(self):

        if not self._text_active:
            return

        object_id = (
            self._active_text_id
        )

        obj = self._get_object(
            object_id
        )

        if obj:

            if self._text_input.strip():

                obj["text"] = (
                    self._text_input
                )

                obj["font_size"] = (
                    self._font_size
                )

                obj["color"] = (
                    self._brush_color.name()
                )

            else:

                try:
                    self._objects.remove(
                        obj
                    )
                except ValueError:
                    pass

        self._text_active = False
        self._active_text_id = None
        self._text_input = ""
        self._text_pos = None

        self._text_cursor_timer.stop()

        self._redraw()
        self.update()

    def _blink_text_cursor(self):

        if not self._text_active:
            return

        self._cursor_visible = (
            not self._cursor_visible
        )

        self.update()

    # =========================================================================
    # SHAPE DRAWING
    # =========================================================================

    def _draw_shape(
        self,
        painter,
        key,
        x1,
        y1,
        x2,
        y2,
        color,
        width,
        preview=False,
    ):

        import math

        lx1 = min(x1, x2)
        ly1 = min(y1, y2)

        lx2 = max(x1, x2)
        ly2 = max(y1, y2)

        mx = (lx1 + lx2) // 2
        my = (ly1 + ly2) // 2

        pen = QPen(
            QColor(color),
            width,
        )

        pen.setCapStyle(
            Qt.PenCapStyle.RoundCap
        )

        pen.setJoinStyle(
            Qt.PenJoinStyle.RoundJoin
        )

        if preview:

            pen.setStyle(
                Qt.PenStyle.DashLine
            )

        painter.setPen(
            pen
        )

        painter.setBrush(
            Qt.BrushStyle.NoBrush
        )

        # ──────────────────────────────────────────────────────────
        # Rectangle
        # ──────────────────────────────────────────────────────────

        if key in (
            "rectangle",
            "er_entity",
        ):

            painter.drawRect(
                lx1,
                ly1,
                lx2 - lx1,
                ly2 - ly1,
            )

        # ──────────────────────────────────────────────────────────
        # Oval
        # ──────────────────────────────────────────────────────────

        elif key == "oval":

            painter.drawEllipse(
                lx1,
                ly1,
                lx2 - lx1,
                ly2 - ly1,
            )

        # ──────────────────────────────────────────────────────────
        # Diamond
        # ──────────────────────────────────────────────────────────

        elif key in (
            "diamond",
            "er_relationship",
        ):

            pts = QPolygon([
                QPoint(mx, ly1),
                QPoint(lx2, my),
                QPoint(mx, ly2),
                QPoint(lx1, my),
            ])

            painter.drawPolygon(
                pts
            )

        # ──────────────────────────────────────────────────────────
        # Line
        # ──────────────────────────────────────────────────────────

        elif key == "line":

            painter.drawLine(
                x1,
                y1,
                x2,
                y2,
            )

        # ──────────────────────────────────────────────────────────
        # Arrow
        # ──────────────────────────────────────────────────────────

        elif key in (
            "arrow",
            "dotted_arrow",
            "double_arrow",
        ):

            if key == "dotted_arrow":

                pen.setStyle(
                    Qt.PenStyle.DashLine
                )

                painter.setPen(
                    pen
                )

            painter.drawLine(
                x1,
                y1,
                x2,
                y2,
            )

            dx = x2 - x1
            dy = y2 - y1

            length = (
                math.hypot(dx, dy)
                or 1
            )

            ux = dx / length
            uy = dy / length

            px = -uy
            py = ux

            tip = 14

            ends = [
                (x2, y2)
            ]

            if key == "double_arrow":
                ends.append(
                    (x1, y1)
                )

            for ex, ey in ends:

                sign = (
                    1
                    if ex == x2
                    else -1
                )

                p1 = QPoint(
                    int(
                        ex
                        - sign * ux * tip
                        + px * 6
                    ),
                    int(
                        ey
                        - sign * uy * tip
                        + py * 6
                    ),
                )

                p2 = QPoint(
                    int(
                        ex
                        - sign * ux * tip
                        - px * 6
                    ),
                    int(
                        ey
                        - sign * uy * tip
                        - py * 6
                    ),
                )

                painter.drawLine(
                    QPoint(ex, ey),
                    p1,
                )

                painter.drawLine(
                    QPoint(ex, ey),
                    p2,
                )

        # ──────────────────────────────────────────────────────────
        # ER Weak Entity
        # ──────────────────────────────────────────────────────────

        elif key == "er_weak_entity":

            pad = 6

            painter.drawRect(
                lx1,
                ly1,
                lx2 - lx1,
                ly2 - ly1,
            )

            painter.drawRect(
                lx1 + pad,
                ly1 + pad,
                lx2 - lx1 - 2 * pad,
                ly2 - ly1 - 2 * pad,
            )

        # ──────────────────────────────────────────────────────────
        # ER Attribute
        # ──────────────────────────────────────────────────────────

        elif key == "er_attribute":

            painter.drawEllipse(
                lx1,
                ly1,
                lx2 - lx1,
                ly2 - ly1,
            )

        # ──────────────────────────────────────────────────────────
        # ER Key / Multi Attribute
        # ──────────────────────────────────────────────────────────

        elif key in (
            "er_key_attr",
            "er_multi_attr",
        ):

            painter.drawEllipse(
                lx1,
                ly1,
                lx2 - lx1,
                ly2 - ly1,
            )

            pad = 6

            painter.drawEllipse(
                lx1 + pad,
                ly1 + pad,
                lx2 - lx1 - 2 * pad,
                ly2 - ly1 - 2 * pad,
            )

        # ──────────────────────────────────────────────────────────
        # ER Weak Relationship
        # ──────────────────────────────────────────────────────────

        elif key == "er_weak_relation":

            pad = 8

            pts1 = QPolygon([
                QPoint(mx, ly1),
                QPoint(lx2, my),
                QPoint(mx, ly2),
                QPoint(lx1, my),
            ])

            pts2 = QPolygon([
                QPoint(mx, ly1 + pad),
                QPoint(lx2 - pad, my),
                QPoint(mx, ly2 - pad),
                QPoint(lx1 + pad, my),
            ])

            painter.drawPolygon(
                pts1
            )

            painter.drawPolygon(
                pts2
            )

        # ──────────────────────────────────────────────────────────
        # UML Class
        # ──────────────────────────────────────────────────────────

        elif key == "uml_class":

            painter.drawRect(
                lx1,
                ly1,
                lx2 - lx1,
                ly2 - ly1,
            )

            h = (
                ly2 - ly1
            )

            painter.drawLine(
                lx1,
                ly1 + h // 3,
                lx2,
                ly1 + h // 3,
            )

            painter.drawLine(
                lx1,
                ly1 + 2 * h // 3,
                lx2,
                ly1 + 2 * h // 3,
            )

        # ──────────────────────────────────────────────────────────
        # UML Interface
        # ──────────────────────────────────────────────────────────

        elif key == "uml_interface":

            painter.drawRect(
                lx1,
                ly1,
                lx2 - lx1,
                ly2 - ly1,
            )

            h = (
                ly2 - ly1
            )

            pen2 = QPen(
                QColor(color),
                width,
                Qt.PenStyle.DashLine,
            )

            painter.setPen(
                pen2
            )

            painter.drawLine(
                lx1,
                ly1 + h // 3,
                lx2,
                ly1 + h // 3,
            )

        # ──────────────────────────────────────────────────────────
        # UML Package
        # ──────────────────────────────────────────────────────────

        elif key == "uml_package":

            tab_w = max(
                40,
                (lx2 - lx1) // 3,
            )

            tab_h = max(
                14,
                (ly2 - ly1) // 5,
            )

            painter.drawRect(
                lx1,
                ly1 + tab_h,
                lx2 - lx1,
                ly2 - ly1 - tab_h,
            )

            painter.drawRect(
                lx1,
                ly1,
                tab_w,
                tab_h,
            )

        # ──────────────────────────────────────────────────────────
        # UML Actor
        # ──────────────────────────────────────────────────────────

        elif key == "uml_actor":

            w = (
                lx2 - lx1
            )

            h = (
                ly2 - ly1
            )

            hr = max(
                4,
                min(w, h) // 5,
            )

            hx = mx
            hy = ly1 + hr

            by1 = hy + hr
            by2 = (
                hy
                + hr
                + h // 2
            )

            painter.drawEllipse(
                hx - hr,
                hy - hr,
                2 * hr,
                2 * hr,
            )

            painter.drawLine(
                hx,
                by1,
                hx,
                by2,
            )

            painter.drawLine(
                lx1,
                by1 + h // 6,
                lx2,
                by1 + h // 6,
            )

            painter.drawLine(
                hx,
                by2,
                lx1,
                ly2,
            )

            painter.drawLine(
                hx,
                by2,
                lx2,
                ly2,
            )

        # ──────────────────────────────────────────────────────────
        # UML Component
        # ──────────────────────────────────────────────────────────

        elif key == "uml_component":

            h = (
                ly2 - ly1
            )

            painter.drawRect(
                lx1 + 20,
                ly1,
                lx2 - lx1 - 20,
                ly2 - ly1,
            )

            painter.drawRect(
                lx1,
                ly1 + h // 4,
                20,
                10,
            )

            painter.drawRect(
                lx1,
                ly1 + h // 2,
                20,
                10,
            )

        # ──────────────────────────────────────────────────────────
        # UML Note
        # ──────────────────────────────────────────────────────────

        elif key == "uml_note":

            fold = min(
                20,
                max(
                    1,
                    (lx2 - lx1) // 4,
                ),
                max(
                    1,
                    (ly2 - ly1) // 4,
                ),
            )

            pts = QPolygon([
                QPoint(lx1, ly1),
                QPoint(lx2 - fold, ly1),
                QPoint(lx2, ly1 + fold),
                QPoint(lx2, ly2),
                QPoint(lx1, ly2),
            ])

            painter.drawPolygon(
                pts
            )

            painter.drawLine(
                lx2 - fold,
                ly1,
                lx2 - fold,
                ly1 + fold,
            )

            painter.drawLine(
                lx2 - fold,
                ly1 + fold,
                lx2,
                ly1 + fold,
            )

        # ──────────────────────────────────────────────────────────
        # UML Inheritance
        # ──────────────────────────────────────────────────────────

        elif key == "uml_inherit":

            painter.drawLine(
                x1,
                y1,
                x2,
                y2,
            )

            dx = x2 - x1
            dy = y2 - y1

            length = (
                math.hypot(dx, dy)
                or 1
            )

            ux = dx / length
            uy = dy / length

            px = -uy
            py = ux

            tip = 16

            tri = QPolygon([
                QPoint(x2, y2),

                QPoint(
                    int(
                        x2
                        - ux * tip
                        + px * tip * 0.5
                    ),
                    int(
                        y2
                        - uy * tip
                        + py * tip * 0.5
                    ),
                ),

                QPoint(
                    int(
                        x2
                        - ux * tip
                        - px * tip * 0.5
                    ),
                    int(
                        y2
                        - uy * tip
                        - py * tip * 0.5
                    ),
                ),
            ])

            painter.drawPolygon(
                tri
            )

        # ──────────────────────────────────────────────────────────
        # Flowchart Document
        # ──────────────────────────────────────────────────────────

        elif key == "flow_document":

            segs = 8

            amp = max(
                6,
                (ly2 - ly1) // 8,
            )

            seg_w = (
                (lx2 - lx1) / segs
                if segs
                else 1
            )

            path_pts = [
                QPoint(lx1, ly1),
                QPoint(lx2, ly1),
                QPoint(lx2, ly2),
            ]

            for i in range(
                segs + 1
            ):

                xi = int(
                    lx2
                    - i * seg_w
                )

                yi = (
                    ly2
                    + (
                        amp
                        if i % 2 == 0
                        else -amp
                    )
                )

                path_pts.append(
                    QPoint(
                        xi,
                        yi,
                    )
                )

            painter.drawPolygon(
                QPolygon(path_pts)
            )

        # ──────────────────────────────────────────────────────────
        # Flowchart Parallelogram
        # ──────────────────────────────────────────────────────────

        elif key == "flow_parallelogram":

            skew = max(
                15,
                (lx2 - lx1) // 5,
            )

            pts = QPolygon([
                QPoint(
                    lx1 + skew,
                    ly1,
                ),
                QPoint(
                    lx2,
                    ly1,
                ),
                QPoint(
                    lx2 - skew,
                    ly2,
                ),
                QPoint(
                    lx1,
                    ly2,
                ),
            ])

            painter.drawPolygon(
                pts
            )

        # ──────────────────────────────────────────────────────────
        # Flowchart Circle
        # ──────────────────────────────────────────────────────────

        elif key == "flow_circle":

            painter.drawEllipse(
                lx1,
                ly1,
                lx2 - lx1,
                ly2 - ly1,
            )

        # ──────────────────────────────────────────────────────────
        # Flowchart Cylinder
        # ──────────────────────────────────────────────────────────

        elif key == "flow_cylinder":

            ry = max(
                10,
                (ly2 - ly1) // 6,
            )

            painter.drawRect(
                lx1,
                ly1 + ry,
                lx2 - lx1,
                ly2 - ly1 - 2 * ry,
            )

            painter.drawEllipse(
                lx1,
                ly1,
                lx2 - lx1,
                2 * ry,
            )

            painter.drawEllipse(
                lx1,
                ly2 - 2 * ry,
                lx2 - lx1,
                2 * ry,
            )

        # ──────────────────────────────────────────────────────────
        # Flowchart Delay
        # ──────────────────────────────────────────────────────────

        elif key == "flow_delay":

            sw = max(
                15,
                (lx2 - lx1) // 4,
            )

            pts = QPolygon([
                QPoint(lx1, ly1),
                QPoint(lx2 - sw, ly1),
                QPoint(lx2, my),
                QPoint(lx2 - sw, ly2),
                QPoint(lx1, ly2),
            ])

            painter.drawPolygon(
                pts
            )

    # =========================================================================
    # OBJECT RENDERING
    # =========================================================================

    def _render_object(
        self,
        painter,
        obj,
    ):

        # ──────────────────────────────────────────────────────────────
        # Stroke
        # ──────────────────────────────────────────────────────────────

        if obj["type"] == "stroke":

            points = obj["points"]

            if not points:
                return

            pen = QPen(
                QColor(obj["color"]),
                obj["width"],
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )

            painter.setPen(
                pen
            )

            if len(points) == 1:

                painter.drawPoint(
                    points[0][0],
                    points[0][1],
                )

                return

            for i in range(
                1,
                len(points),
            ):

                x1, y1 = points[
                    i - 1
                ]

                x2, y2 = points[
                    i
                ]

                painter.drawLine(
                    x1,
                    y1,
                    x2,
                    y2,
                )

            return

        # ──────────────────────────────────────────────────────────────
        # Shape
        # ──────────────────────────────────────────────────────────────

        if obj["type"] == "shape":

            self._draw_shape(
                painter,
                obj["shape"],
                obj["x1"],
                obj["y1"],
                obj["x2"],
                obj["y2"],
                obj["color"],
                obj["width"],
                preview=False,
            )

            return

        # ──────────────────────────────────────────────────────────────
        # Text
        # ──────────────────────────────────────────────────────────────

        if obj["type"] == "text":

            if (
                obj["id"]
                == self._active_text_id
            ):
                return

            font = QFont(
                "Arial",
                obj["font_size"],
            )

            painter.setFont(
                font
            )

            painter.setPen(
                QPen(
                    QColor(
                        obj["color"]
                    )
                )
            )

            metrics = QFontMetrics(
                font
            )

            lines = obj["text"].split(
                "\n"
            )

            for i, line in enumerate(
                lines
            ):

                painter.drawText(
                    obj["x"],
                    obj["y"]
                    + i * metrics.lineSpacing(),
                    line,
                )

    # =========================================================================
    # REDRAW
    # =========================================================================

    def _redraw(self):

        self._pixmap.fill(
            QColor("#ffffff")
        )

        painter = QPainter(
            self._pixmap
        )

        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )

        for obj in self._objects:

            self._render_object(
                painter,
                obj,
            )

        painter.end()

    # =========================================================================
    # PAINT EVENT
    # =========================================================================

    def paintEvent(self, event):

        painter = QPainter(
            self
        )

        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )

        # ──────────────────────────────────────────────────────────────
        # Base canvas
        # ──────────────────────────────────────────────────────────────

        painter.drawPixmap(
            -self._scroll_x,
            -self._scroll_y,
            self._pixmap,
        )

        # ──────────────────────────────────────────────────────────────
        # Preview
        # ──────────────────────────────────────────────────────────────

        if self._preview_pixmap:

            painter.drawPixmap(
                -self._scroll_x,
                -self._scroll_y,
                self._preview_pixmap,
            )

        # ──────────────────────────────────────────────────────────────
        # Active text
        # ──────────────────────────────────────────────────────────────

        if (
            self._text_active
            and self._text_pos is not None
        ):

            font = QFont(
                "Arial",
                self._font_size,
            )

            painter.setFont(
                font
            )

            painter.setPen(
                QPen(
                    self._brush_color
                )
            )

            metrics = QFontMetrics(
                font
            )

            screen_x = (
                self._text_pos.x()
                - self._scroll_x
            )

            screen_y = (
                self._text_pos.y()
                - self._scroll_y
            )

            lines = (
                self._text_input
                .split("\n")
            )

            for i, line in enumerate(
                lines
            ):

                painter.drawText(
                    screen_x,
                    screen_y
                    + i * metrics.lineSpacing(),
                    line,
                )

            # Cursor
            if self._cursor_visible:

                current_line = (
                    lines[-1]
                    if lines
                    else ""
                )

                cursor_x = (
                    screen_x
                    + metrics.horizontalAdvance(
                        current_line
                    )
                )

                cursor_y = (
                    screen_y
                    + (
                        len(lines) - 1
                    )
                    * metrics.lineSpacing()
                )

                painter.drawLine(
                    cursor_x,
                    cursor_y - metrics.ascent(),
                    cursor_x,
                    cursor_y + metrics.descent(),
                )

        # ──────────────────────────────────────────────────────────────
        # Selection box + handles
        # ──────────────────────────────────────────────────────────────

        if self._selected_object_ids:

            bx1, by1, bx2, by2 = (
                self._bbox_of_objects()
            )

            pad = 6

            x1 = (
                bx1
                - pad
                - self._scroll_x
            )

            y1 = (
                by1
                - pad
                - self._scroll_y
            )

            x2 = (
                bx2
                + pad
                - self._scroll_x
            )

            y2 = (
                by2
                + pad
                - self._scroll_y
            )

            pen = QPen(
                QColor("#3b82f6"),
                1,
                Qt.PenStyle.DashLine,
            )

            painter.setPen(
                pen
            )

            painter.setBrush(
                Qt.BrushStyle.NoBrush
            )

            painter.drawRect(
                int(x1),
                int(y1),
                int(x2 - x1),
                int(y2 - y1),
            )

            painter.setPen(
                QPen(
                    QColor("#ffffff"),
                    1,
                )
            )

            painter.setBrush(
                QColor("#3b82f6")
            )

            for hx, hy in [
                (x1, y1),
                (x2, y1),
                (x2, y2),
                (x1, y2),
            ]:

                painter.drawRect(
                    int(hx - 4),
                    int(hy - 4),
                    8,
                    8,
                )

        painter.end()

    # =========================================================================
    # MOUSE PRESS
    # =========================================================================

    def mousePressEvent(self, event):

        if event.button() != (
            Qt.MouseButton.LeftButton
        ):
            return

        self.setFocus()

        cp = self._canvas_pt(
            event.position().toPoint()
        )

        cx = cp.x()
        cy = cp.y()

        # ──────────────────────────────────────────────────────────────
        # Text mode
        # ──────────────────────────────────────────────────────────────

        if self._text_mode:

            hit = self._find_object_at(
                cx,
                cy,
            )

            if hit is not None:

                obj = self._get_object(
                    hit
                )

                if (
                    obj
                    and obj["type"] == "text"
                    and hit != self._active_text_id
                ):

                    self._save_undo()

                    self._select_object(
                        hit
                    )

                    self._dragging_object = True

                    self._drag_last_pos = (
                        cx,
                        cy,
                    )

                    self.setCursor(
                        Qt.CursorShape.SizeAllCursor
                    )

                    return

            self._deselect_objects()

            self._create_text_cursor(
                cx,
                cy,
            )

            return

        # ──────────────────────────────────────────────────────────────
        # Shape mode
        # ──────────────────────────────────────────────────────────────

        if self._shape_mode:

            self._commit_text()

            self._deselect_objects()

            self._shape_start = (
                cx,
                cy,
            )

            return

        # ──────────────────────────────────────────────────────────────
        # Existing object
        # ──────────────────────────────────────────────────────────────

        hit = self._find_object_at(
            cx,
            cy,
        )

        if hit is not None:

            self._save_undo()

            self._select_object(
                hit
            )

            self._dragging_object = True

            self._drag_last_pos = (
                cx,
                cy,
            )

            self.setCursor(
                Qt.CursorShape.SizeAllCursor
            )

            return

        # ──────────────────────────────────────────────────────────────
        # Freehand
        # ──────────────────────────────────────────────────────────────

        self._deselect_objects()

        self._save_undo()

        self._current_stroke = {
            "id": self._new_object_id(),
            "type": "stroke",
            "points": [
                (cx, cy)
            ],
            "color": self._brush_color.name(),
            "width": self._brush_size,
        }

        self._objects.append(
            self._current_stroke
        )

        self._drawing = True

        self.update()

    # =========================================================================
    # MOUSE MOVE
    # =========================================================================

    def mouseMoveEvent(self, event):

        cp = self._canvas_pt(
            event.position().toPoint()
        )

        cx = cp.x()
        cy = cp.y()

        # ──────────────────────────────────────────────────────────────
        # Drag selected object
        # ──────────────────────────────────────────────────────────────

        if (
            self._dragging_object
            and self._drag_last_pos is not None
        ):

            dx = (
                cx
                - self._drag_last_pos[0]
            )

            dy = (
                cy
                - self._drag_last_pos[1]
            )

            if dx or dy:

                self._move_selected(
                    dx,
                    dy,
                )

                self._drag_last_pos = (
                    cx,
                    cy,
                )

            return

        # ──────────────────────────────────────────────────────────────
        # Shape preview
        # ──────────────────────────────────────────────────────────────

        if (
            self._shape_mode
            and self._shape_start
        ):

            preview = self._pixmap.copy()

            painter = QPainter(
                preview
            )

            painter.setRenderHint(
                QPainter.RenderHint.Antialiasing
            )

            self._draw_shape(
                painter,
                self._shape_mode,
                self._shape_start[0],
                self._shape_start[1],
                cx,
                cy,
                self._brush_color.name(),
                self._brush_size,
                preview=True,
            )

            painter.end()

            self._preview_pixmap = (
                preview
            )

            self.update()

            return

        # ──────────────────────────────────────────────────────────────
        # Freehand drawing
        # ──────────────────────────────────────────────────────────────

        if (
            self._drawing
            and self._current_stroke
        ):

            self._current_stroke[
                "points"
            ].append(
                (cx, cy)
            )

            self._redraw()

            self.update()

    # =========================================================================
    # MOUSE RELEASE
    # =========================================================================

    def mouseReleaseEvent(self, event):

        if event.button() != (
            Qt.MouseButton.LeftButton
        ):
            return

        cp = self._canvas_pt(
            event.position().toPoint()
        )

        cx = cp.x()
        cy = cp.y()

        # ──────────────────────────────────────────────────────────────
        # Finish dragging
        # ──────────────────────────────────────────────────────────────

        if self._dragging_object:

            self._dragging_object = False
            self._drag_last_pos = None

            self.setCursor(
                Qt.CursorShape.IBeamCursor
                if self._text_mode
                else Qt.CursorShape.CrossCursor
            )

            return

        # ──────────────────────────────────────────────────────────────
        # Finish shape
        # ──────────────────────────────────────────────────────────────

        if (
            self._shape_mode
            and self._shape_start
        ):

            sx, sy = self._shape_start

            self._preview_pixmap = None

            if (
                abs(cx - sx) > 5
                or
                abs(cy - sy) > 5
            ):

                self._save_undo()

                obj = {
                    "id": self._new_object_id(),
                    "type": "shape",
                    "shape": self._shape_mode,
                    "x1": sx,
                    "y1": sy,
                    "x2": cx,
                    "y2": cy,
                    "color": self._brush_color.name(),
                    "width": self._brush_size,
                }

                self._objects.append(
                    obj
                )

                self._redraw()

            self._shape_start = None

            # Existing behavior: shape mode automatically exits.
            self._shape_mode = None

            self.shape_mode_ended.emit()

            self.setCursor(
                Qt.CursorShape.CrossCursor
            )

            self.update()

            return

        # ──────────────────────────────────────────────────────────────
        # Finish freehand
        # ──────────────────────────────────────────────────────────────

        self._drawing = False
        self._current_stroke = None

        self._redraw()
        self.update()

    # =========================================================================
    # DOUBLE CLICK
    # =========================================================================

    def mouseDoubleClickEvent(self, event):

        if event.button() != (
            Qt.MouseButton.LeftButton
        ):
            return

        cp = self._canvas_pt(
            event.position().toPoint()
        )

        cx = cp.x()
        cy = cp.y()

        self._deselect_objects()

        # Double-click means text editing.
        self._shape_mode = None
        self._text_mode = True

        self.setCursor(
            Qt.CursorShape.IBeamCursor
        )

        clicked_text = self._find_text_at(
            cx,
            cy,
        )

        if clicked_text is not None:

            if (
                self._active_text_id is not None
                and
                self._active_text_id != clicked_text
            ):

                self._commit_text()

            if (
                self._active_text_id
                != clicked_text
            ):

                self._reopen_text(
                    clicked_text
                )

            return

        if self._active_text_id is not None:
            self._commit_text()

        self._create_text_cursor(
            cx,
            cy,
        )

    # =========================================================================
    # KEYBOARD
    # =========================================================================

    def keyPressEvent(self, event):

        key = event.key()

        # ──────────────────────────────────────────────────────────────
        # TEXT EDITING
        # ──────────────────────────────────────────────────────────────

        if self._text_active:

            if key == Qt.Key.Key_Escape:

                obj = self._get_object(
                    self._active_text_id
                )

                if obj:

                    try:
                        self._objects.remove(
                            obj
                        )
                    except ValueError:
                        pass

                self._text_active = False
                self._active_text_id = None
                self._text_input = ""
                self._text_pos = None

                self._text_cursor_timer.stop()

                self._redraw()
                self.update()

                return

            if key == Qt.Key.Key_Backspace:

                self._text_input = (
                    self._text_input[:-1]
                )

                self._cursor_visible = True

                self.update()

                return

            if key == Qt.Key.Key_Return:

                self._text_input += "\n"

                self._cursor_visible = True

                self.update()

                return

            text = event.text()

            if (
                text
                and ord(text[0]) >= 32
            ):

                self._text_input += text

                self._cursor_visible = True

                self.update()

            return

        # ──────────────────────────────────────────────────────────────
        # DELETE SELECTED OBJECT
        # ──────────────────────────────────────────────────────────────

        if key == Qt.Key.Key_Delete:

            if self._selected_object_ids:
                self.delete_selected()

            return

        # ──────────────────────────────────────────────────────────────
        # CANVAS SCROLL
        # ──────────────────────────────────────────────────────────────

        step = 40

        max_x = max(
            0,
            CANVAS_W - self.width(),
        )

        max_y = max(
            0,
            CANVAS_H - self.height(),
        )

        if key == Qt.Key.Key_W:

            self._scroll_y = max(
                0,
                self._scroll_y - step,
            )

            self.update()

        elif key == Qt.Key.Key_S:

            self._scroll_y = min(
                max_y,
                self._scroll_y + step,
            )

            self.update()

        elif key == Qt.Key.Key_A:

            self._scroll_x = max(
                0,
                self._scroll_x - step,
            )

            self.update()

        elif key == Qt.Key.Key_D:

            self._scroll_x = min(
                max_x,
                self._scroll_x + step,
            )

            self.update()

        elif key == Qt.Key.Key_Z:

            self.undo()

    # =========================================================================
    # DELETE
    # =========================================================================

    def delete_selected(self):

        if not self._selected_object_ids:
            return

        self._save_undo()

        selected = set(
            self._selected_object_ids
        )

        self._objects = [
            obj
            for obj in self._objects
            if obj["id"] not in selected
        ]

        self._selected_object_ids = []

        self._redraw()
        self.update()

    # =========================================================================
    # WHEEL
    # =========================================================================

    def wheelEvent(self, event):

        delta = event.angleDelta().y()
        step = 40

        max_x = max(
            0,
            CANVAS_W - self.width(),
        )

        max_y = max(
            0,
            CANVAS_H - self.height(),
        )

        if (
            event.modifiers()
            & Qt.KeyboardModifier.ShiftModifier
        ):

            self._scroll_x = max(
                0,
                min(
                    max_x,
                    self._scroll_x
                    + (
                        -step
                        if delta > 0
                        else step
                    ),
                ),
            )

        else:

            self._scroll_y = max(
                0,
                min(
                    max_y,
                    self._scroll_y
                    + (
                        -step
                        if delta > 0
                        else step
                    ),
                ),
            )

        self.update()

    # =========================================================================
    # SAVE
    # =========================================================================

    def save_to_file(
        self,
        path: str,
    ) -> bool:

        self._commit_text()

        try:

            self._redraw()

            return self._pixmap.save(
                path
            )

        except Exception:
            return False


# ──────────────────────────────────────────────────────────────────────────────
# CANVAS SECTION
# ──────────────────────────────────────────────────────────────────────────────

class CanvasSection(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self._active_shape = None

        self._build_ui()

    # =========================================================================
    # UI
    # =========================================================================

    def _build_ui(self):

        root = QVBoxLayout(
            self
        )

        root.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        root.setSpacing(0)

        # ──────────────────────────────────────────────────────────────
        # Toolbar
        # ──────────────────────────────────────────────────────────────

        toolbar = QFrame()

        toolbar.setObjectName(
            "toolbar_card"
        )

        toolbar.setFixedHeight(
            52
        )

        tb = QHBoxLayout(
            toolbar
        )

        tb.setContentsMargins(
            10,
            6,
            10,
            6,
        )

        tb.setSpacing(6)

        lbl = QLabel(
            "🎨  Canvas"
        )

        lbl.setStyleSheet(
            "font-size:16px;"
            "font-weight:bold;"
            "color:#e0e0ff;"
        )

        tb.addWidget(
            lbl
        )

        self._vsep(toolbar)

        # ──────────────────────────────────────────────────────────────
        # Color
        # ──────────────────────────────────────────────────────────────

        tb.addWidget(
            QLabel("COLOR:")
        )

        self._color_btns = []

        for hex_col, name in CANVAS_COLORS:

            btn = QPushButton()

            btn.setFixedSize(
                26,
                26,
            )

            btn.setToolTip(
                name
            )

            btn.setStyleSheet(
                f"background:{hex_col};"
                "border-radius:13px;"
                "border:2px solid transparent;"
            )

            btn.clicked.connect(
                lambda _,
                c=hex_col,
                b=btn:
                self._set_color(c, b)
            )

            tb.addWidget(
                btn
            )

            self._color_btns.append(
                (btn, hex_col)
            )

        self._vsep(toolbar)

        # ──────────────────────────────────────────────────────────────
        # Brush
        # ──────────────────────────────────────────────────────────────

        tb.addWidget(
            QLabel("BRUSH:")
        )

        self._brush_slider = QSlider(
            Qt.Orientation.Horizontal
        )

        self._brush_slider.setRange(
            1,
            20
        )

        self._brush_slider.setValue(
            3
        )

        self._brush_slider.setFixedWidth(
            80
        )

        self._brush_lbl = QLabel(
            "3"
        )

        self._brush_lbl.setFixedWidth(
            20
        )

        self._brush_slider.valueChanged.connect(
            self._on_brush
        )

        tb.addWidget(
            self._brush_slider
        )

        tb.addWidget(
            self._brush_lbl
        )

        self._vsep(toolbar)

        # ──────────────────────────────────────────────────────────────
        # Font
        # ──────────────────────────────────────────────────────────────

        tb.addWidget(
            QLabel("FONT:")
        )

        self._font_slider = QSlider(
            Qt.Orientation.Horizontal
        )

        self._font_slider.setRange(
            8,
            72
        )

        self._font_slider.setValue(
            20
        )

        self._font_slider.setFixedWidth(
            80
        )

        self._font_lbl = QLabel(
            "20"
        )

        self._font_lbl.setFixedWidth(
            24
        )

        self._font_slider.valueChanged.connect(
            self._on_font
        )

        tb.addWidget(
            self._font_slider
        )

        tb.addWidget(
            self._font_lbl
        )

        self._vsep(toolbar)

        # ──────────────────────────────────────────────────────────────
        # Text
        # ──────────────────────────────────────────────────────────────

        self._text_btn = QPushButton(
            "🔤 Text"
        )

        self._text_btn.setObjectName(
            "action_btn"
        )

        self._text_btn.setFixedHeight(
            34
        )

        self._text_btn.setCheckable(
            True
        )

        self._text_btn.toggled.connect(
            self._toggle_text
        )

        tb.addWidget(
            self._text_btn
        )

        # ──────────────────────────────────────────────────────────────
        # Undo
        # ──────────────────────────────────────────────────────────────

        undo_btn = QPushButton(
            "↩ Undo"
        )

        undo_btn.setObjectName(
            "action_btn"
        )

        undo_btn.setFixedHeight(
            34
        )

        undo_btn.clicked.connect(
            self._undo
        )

        tb.addWidget(
            undo_btn
        )

        # ──────────────────────────────────────────────────────────────
        # Clear
        # ──────────────────────────────────────────────────────────────

        clr_btn = QPushButton(
            "🗑 Clear"
        )

        clr_btn.setObjectName(
            "danger_btn"
        )

        clr_btn.setFixedHeight(
            34
        )

        clr_btn.clicked.connect(
            self._clear
        )

        tb.addWidget(
            clr_btn
        )

        self._vsep(toolbar)

        # ──────────────────────────────────────────────────────────────
        # Save
        # ──────────────────────────────────────────────────────────────

        save_btn = QPushButton(
            "💾 Save"
        )

        save_btn.setObjectName(
            "action_btn"
        )

        save_btn.setFixedHeight(
            34
        )

        save_btn.clicked.connect(
            self._save
        )

        tb.addWidget(
            save_btn
        )

        # ──────────────────────────────────────────────────────────────
        # AI
        # ──────────────────────────────────────────────────────────────

        ai_btn = QPushButton(
            "🤖 AI Summary"
        )

        ai_btn.setObjectName(
            "action_btn"
        )

        ai_btn.setFixedHeight(
            34
        )

        ai_btn.setStyleSheet(
            "background-color:#4c1d95;"
            "color:#fff;"
            "border:none;"
            "border-radius:8px;"
            "padding:4px 10px;"
            "font-size:12px;"
            "font-weight:bold;"
        )

        ai_btn.clicked.connect(
            self._ai_summary
        )

        tb.addWidget(
            ai_btn
        )

        self._ai_status = QLabel(
            ""
        )

        self._ai_status.setStyleSheet(
            "color:#64748b;"
            "font-size:10px;"
        )

        self._ai_status.setMaximumWidth(
            200
        )

        tb.addWidget(
            self._ai_status
        )

        self._mode_lbl = QLabel(
            "MODE: DRAW"
        )

        self._mode_lbl.setStyleSheet(
            "color:#22c55e;"
            "font-weight:bold;"
            "font-size:11px;"
        )

        tb.addWidget(
            self._mode_lbl
        )

        tb.addStretch()

        root.addWidget(
            toolbar
        )

        # ──────────────────────────────────────────────────────────────
        # Body
        # ──────────────────────────────────────────────────────────────

        body = QWidget()

        body_lay = QHBoxLayout(
            body
        )

        body_lay.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        body_lay.setSpacing(0)

        # ──────────────────────────────────────────────────────────────
        # Shapes sidebar
        # ──────────────────────────────────────────────────────────────

        shapes_panel = QScrollArea()

        shapes_panel.setFixedWidth(
            180
        )

        shapes_panel.setWidgetResizable(
            True
        )

        shapes_panel.setStyleSheet(
            "QScrollArea {"
            "background:#0f172a;"
            "border:none;"
            "}"
            "QWidget {"
            "background:#0f172a;"
            "}"
        )

        shapes_inner = QWidget()

        shapes_inner.setStyleSheet(
            "background:#0f172a;"
        )

        shapes_vlay = QVBoxLayout(
            shapes_inner
        )

        shapes_vlay.setContentsMargins(
            6,
            10,
            6,
            10,
        )

        shapes_vlay.setSpacing(
            4
        )

        hdr = QLabel(
            "SHAPES"
        )

        hdr.setStyleSheet(
            "color:#94a3b8;"
            "font-size:10px;"
            "font-weight:bold;"
        )

        hdr.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        shapes_vlay.addWidget(
            hdr
        )

        ACCENT = {
            "ER Diagram": "#7c3aed",
            "UML Diagram": "#0284c7",
            "Flowchart": "#059669",
        }

        self._shape_btns = {}

        for group_name, shapes in (
            SHAPE_CATALOG.items()
        ):

            accent = ACCENT.get(
                group_name,
                "#334155",
            )

            grp_btn = QPushButton(
                f"▼  {group_name}"
            )

            grp_btn.setStyleSheet(
                "background:#1e293b;"
                "color:#94a3b8;"
                "border:none;"
                "border-radius:6px;"
                "padding:6px 8px;"
                "text-align:left;"
                "font-size:11px;"
                "font-weight:bold;"
            )

            grp_btn.setCheckable(
                True
            )

            shapes_vlay.addWidget(
                grp_btn
            )

            grid_widget = QWidget()

            grid_widget.setStyleSheet(
                "background:#131c2e;"
                "border-radius:6px;"
            )

            grid_widget.setVisible(
                False
            )

            grid = QGridLayout(
                grid_widget
            )

            grid.setContentsMargins(
                4,
                4,
                4,
                4,
            )

            grid.setSpacing(
                4
            )

            for idx, (
                shape_name,
                shape_icon,
                shape_key,
            ) in enumerate(
                shapes
            ):

                r, c = divmod(
                    idx,
                    3,
                )

                cell = QWidget()

                cell_lay = QVBoxLayout(
                    cell
                )

                cell_lay.setContentsMargins(
                    2,
                    2,
                    2,
                    2,
                )

                cell_lay.setSpacing(
                    2
                )

                cell_lay.setAlignment(
                    Qt.AlignmentFlag.AlignCenter
                )

                sbtn = QPushButton(
                    shape_icon
                )

                sbtn.setCheckable(
                    True
                )

                sbtn.setFixedSize(
                    44,
                    38,
                )

                sbtn.setStyleSheet(
                    f"background:#1e293b;"
                    f"color:#e2e8f0;"
                    f"border:none;"
                    f"border-radius:6px;"
                    f"font-size:17px;"
                    f"QPushButton:checked {{"
                    f"background:{accent};"
                    f"color:#fff;"
                    f"}}"
                )

                sbtn.setToolTip(
                    shape_name
                )

                sbtn.clicked.connect(
                    lambda _,
                    key=shape_key,
                    name=shape_name,
                    btn=sbtn:
                    self._set_shape(
                        key,
                        name,
                        btn,
                    )
                )

                lbl = QLabel(
                    shape_name
                )

                lbl.setAlignment(
                    Qt.AlignmentFlag.AlignCenter
                )

                lbl.setStyleSheet(
                    "color:#64748b;"
                    "font-size:8px;"
                )

                lbl.setWordWrap(
                    True
                )

                lbl.setFixedWidth(
                    52
                )

                cell_lay.addWidget(
                    sbtn,
                    alignment=Qt.AlignmentFlag.AlignCenter,
                )

                cell_lay.addWidget(
                    lbl,
                    alignment=Qt.AlignmentFlag.AlignCenter,
                )

                grid.addWidget(
                    cell,
                    r,
                    c,
                )

                self._shape_btns[
                    shape_key
                ] = sbtn

            def on_group_toggled(
                checked,
                gw=grid_widget,
                gb=grp_btn,
                gn=group_name,
                ac=accent,
            ):

                gw.setVisible(
                    checked
                )

                gb.setText(
                    (
                        "▲  "
                        if checked
                        else
                        "▼  "
                    )
                    + gn
                )

                gb.setStyleSheet(
                    "background:"
                    f"{ac if checked else '#1e293b'};"
                    "color:"
                    f"{'#fff' if checked else '#94a3b8'};"
                    "border:none;"
                    "border-radius:6px;"
                    "padding:6px 8px;"
                    "text-align:left;"
                    "font-size:11px;"
                    "font-weight:bold;"
                )

            grp_btn.toggled.connect(
                on_group_toggled
            )

            shapes_vlay.addWidget(
                grid_widget
            )

        shapes_vlay.addStretch()

        shapes_panel.setWidget(
            shapes_inner
        )

        body_lay.addWidget(
            shapes_panel
        )

        # ──────────────────────────────────────────────────────────────
        # Canvas
        # ──────────────────────────────────────────────────────────────

        self._canvas = DrawingCanvas()

        self._canvas.shape_mode_ended.connect(
            self._on_shape_drawn
        )

        self._set_color(
            CANVAS_COLORS[0][0],
            self._color_btns[0][0],
        )

        body_lay.addWidget(
            self._canvas,
            stretch=1,
        )

        root.addWidget(
            body,
            stretch=1,
        )

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _vsep(self, parent):

        sep = QFrame(
            parent
        )

        sep.setFrameShape(
            QFrame.Shape.VLine
        )

        sep.setStyleSheet(
            "color:#334155;"
        )

        sep.setFixedWidth(
            1
        )

        parent.layout().addWidget(
            sep
        )

    # =========================================================================
    # COLOR
    # =========================================================================

    def _set_color(
        self,
        hex_col: str,
        active_btn: QPushButton,
    ):

        self._canvas.set_color(
            hex_col
        )

        for btn, col in (
            self._color_btns
        ):

            border = (
                "#ffffff"
                if btn is active_btn
                else "transparent"
            )

            btn.setStyleSheet(
                f"background:{col};"
                "border-radius:13px;"
                f"border:2px solid {border};"
            )

    # =========================================================================
    # BRUSH
    # =========================================================================

    def _on_brush(
        self,
        value,
    ):

        self._brush_lbl.setText(
            str(value)
        )

        self._canvas.set_brush_size(
            value
        )

    # =========================================================================
    # FONT
    # =========================================================================

    def _on_font(
        self,
        value,
    ):

        self._font_lbl.setText(
            str(value)
        )

        self._canvas.set_font_size(
            value
        )

    # =========================================================================
    # TEXT MODE
    # =========================================================================

    def _toggle_text(
        self,
        checked,
    ):

        self._canvas.set_text_mode(
            checked
        )

        if checked:

            self._text_btn.setText(
                "✏ Text ON"
            )

            self._mode_lbl.setText(
                "MODE: TEXT"
            )

            self._mode_lbl.setStyleSheet(
                "color:#f59e0b;"
                "font-weight:bold;"
                "font-size:11px;"
            )

            self._deselect_all_shapes()

        else:

            self._text_btn.setText(
                "🔤 Text"
            )

            self._mode_lbl.setText(
                "MODE: DRAW"
            )

            self._mode_lbl.setStyleSheet(
                "color:#22c55e;"
                "font-weight:bold;"
                "font-size:11px;"
            )

    # =========================================================================
    # SHAPE
    # =========================================================================

    def _set_shape(
        self,
        key: str,
        name: str,
        btn: QPushButton,
    ):

        self._deselect_all_shapes()

        btn.setChecked(
            True
        )

        self._active_shape = key

        self._canvas.set_shape_mode(
            key
        )

        self._text_btn.setChecked(
            False
        )

        self._mode_lbl.setText(
            f"SHAPE: {name.upper()}"
        )

        self._mode_lbl.setStyleSheet(
            "color:#a78bfa;"
            "font-weight:bold;"
            "font-size:11px;"
        )

    def _on_shape_drawn(self):

        self._deselect_all_shapes()

        self._active_shape = None

        self._mode_lbl.setText(
            "MODE: DRAW"
        )

        self._mode_lbl.setStyleSheet(
            "color:#22c55e;"
            "font-weight:bold;"
            "font-size:11px;"
        )

    def _deselect_all_shapes(self):

        for btn in (
            self._shape_btns.values()
        ):

            btn.setChecked(
                False
            )

    # =========================================================================
    # UNDO
    # =========================================================================

    def _undo(self):
        self._canvas.undo()

    # =========================================================================
    # CLEAR
    # =========================================================================

    def _clear(self):

        if qmsg_ask(
            self,
            "Clear canvas",
            "Clear all drawings?",
        ):

            self._canvas.clear_canvas()

    # =========================================================================
    # SAVE
    # =========================================================================

    def _save(self):

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Canvas",
            str(
                SAVED_OUTPUTS_DIR
                / "canvas_save.png"
            ),
            "PNG Image (*.png)",
        )

        if not path:
            return

        if self._canvas.save_to_file(
            path
        ):

            try:

                (
                    BASE_DIR
                    / "last_output.json"
                ).write_text(
                    json.dumps(
                        {
                            "type": "canvas",
                            "path": str(
                                Path(
                                    path
                                ).resolve()
                            ),
                        }
                    ),
                    encoding="utf-8",
                )

            except Exception:
                pass

            qmsg_info(
                self,
                "Saved",
                f"Canvas saved to:\n{path}",
            )

        else:

            qmsg_err(
                self,
                "Save failed",
                "Could not save the canvas image.",
            )

    # =========================================================================
    # AI SUMMARY
    # =========================================================================

    def _ai_summary(self):

        import threading

        try:

            from ocr_pipeline import (
                ocr_and_summarize,
            )

        except ImportError:

            self._ai_status.setText(
                "❌ ocr_pipeline.py not found"
            )

            self._ai_status.setStyleSheet(
                "color:#ef4444;"
                "font-size:10px;"
            )

            return

        last_output = (
            BASE_DIR
            / "last_output.json"
        )

        if not last_output.exists():

            self._ai_status.setText(
                "⚠ Save canvas first"
            )

            self._ai_status.setStyleSheet(
                "color:#f59e0b;"
                "font-size:10px;"
            )

            return

        try:

            data = json.loads(
                last_output.read_text(
                    encoding="utf-8"
                )
            )

        except Exception:

            self._ai_status.setText(
                "⚠ Could not read last_output.json"
            )

            self._ai_status.setStyleSheet(
                "color:#f59e0b;"
                "font-size:10px;"
            )

            return

        if (
            not data
            or "path" not in data
        ):

            self._ai_status.setText(
                "⚠ Save canvas first"
            )

            self._ai_status.setStyleSheet(
                "color:#f59e0b;"
                "font-size:10px;"
            )

            return

        self._ai_status.setText(
            "⏳ Analyzing…"
        )

        self._ai_status.setStyleSheet(
            "color:#f59e0b;"
            "font-size:10px;"
        )

        def worker():

            try:

                result = (
                    ocr_and_summarize(
                        data["path"],
                    )
                )

            except Exception as e:

                QTimer.singleShot(
                    0,
                    lambda:
                    self._set_ai_error(
                        str(e)
                    )
                )

                return

            if result.error:

                QTimer.singleShot(
                    0,
                    lambda:
                    self._set_ai_error(
                        result.error
                    )
                )

                return

            QTimer.singleShot(
                0,
                lambda:
                self._show_ai_result(
                    result.summary
                )
            )

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

    def _set_ai_error(
        self,
        message,
    ):

        self._ai_status.setText(
            f"❌ {message}"
        )

        self._ai_status.setStyleSheet(
            "color:#ef4444;"
            "font-size:10px;"
        )

    def _show_ai_result(
        self,
        summary,
    ):

        self._ai_status.setText(
            "✅ Summary ready"
        )

        self._ai_status.setStyleSheet(
            "color:#22c55e;"
            "font-size:10px;"
        )

        dlg = QDialog(
            self
        )

        dlg.setWindowTitle(
            "🤖 AI Summary of Canvas"
        )

        dlg.resize(
            600,
            400,
        )

        dlg.setStyleSheet(
            "background:#0f172a;"
            "color:#e2e8f0;"
        )

        lay = QVBoxLayout(
            dlg
        )

        lay.setContentsMargins(
            16,
            16,
            16,
            16,
        )

        hdr = QLabel(
            "🤖  AI Summary"
        )

        hdr.setStyleSheet(
            "font-size:14px;"
            "font-weight:bold;"
            "color:#e2e8f0;"
        )

        lay.addWidget(
            hdr
        )

        box = QTextEdit()

        box.setReadOnly(
            True
        )

        box.setStyleSheet(
            "background:#161925;"
            "color:#e2e8f0;"
            "border-radius:8px;"
            "font-size:12px;"
            "padding:8px;"
        )

        box.setPlainText(
            summary
            or
            "(No summary generated)"
        )

        lay.addWidget(
            box
        )

        close_btn = QPushButton(
            "Close"
        )

        close_btn.setObjectName(
            "action_btn"
        )

        close_btn.clicked.connect(
            dlg.accept
        )

        lay.addWidget(
            close_btn,
            alignment=Qt.AlignmentFlag.AlignRight,
        )

        dlg.exec()