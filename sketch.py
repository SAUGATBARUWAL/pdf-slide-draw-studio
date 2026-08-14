# sketch.py

from __future__ import annotations

import time
from collections import deque

import cv2
import mediapipe as mp
import numpy as np

from PyQt6.QtCore import (
    Qt,
    QTimer,
    QThread,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QPixmap,
    QImage,
)
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QLabel,
    QPushButton,
    QLineEdit,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QSplitter,
    QFileDialog,
)

from config import (
    SAVED_OUTPUTS_DIR,

    SKETCH_COLORS_BGR,
    SKETCH_COLORS_HEX,
    SKETCH_COLOR_NAMES,

    SKETCH_PINCH_THRESHOLD,
    SKETCH_SMOOTHING,

    SKETCH_UNDO_COOLDOWN,
    SKETCH_BUTTON_COOLDOWN,

    SKETCH_CAM_W,
    SKETCH_CAM_H,

    SKETCH_GUIDE_MARGIN,
)

from utils import (
    qmsg_info,
    qmsg_warn,
    qmsg_err,
)


# ──────────────────────────────────────────────────────────────────────────────
# MEDIA PIPE CAMERA WORKER
# ──────────────────────────────────────────────────────────────────────────────

class _SketchCamWorker(QThread):

    frame_ready = pyqtSignal(object, object)
    status_sig = pyqtSignal(str, str)
    color_sig = pyqtSignal(int)

    def __init__(self, state: dict):
        super().__init__()
        self._s = state

    # ──────────────────────────────────────────────────────────────────────
    # CAMERA OPEN
    # ──────────────────────────────────────────────────────────────────────

    def _open_camera(self, index: int):

        backends = [
            cv2.CAP_DSHOW,
            cv2.CAP_MSMF,
            cv2.CAP_ANY,
        ]

        for backend in backends:

            cap = None

            try:
                cap = cv2.VideoCapture(
                    index,
                    backend
                )

                if not cap.isOpened():
                    cap.release()
                    continue

                cap.set(
                    cv2.CAP_PROP_FRAME_WIDTH,
                    SKETCH_CAM_W
                )

                cap.set(
                    cv2.CAP_PROP_FRAME_HEIGHT,
                    SKETCH_CAM_H
                )

                # Test that this backend actually returns frames.
                for _ in range(5):

                    ret, frame = cap.read()

                    if ret and frame is not None:
                        return cap

                    time.sleep(0.05)

                cap.release()

            except Exception:
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass

        return cv2.VideoCapture(index)

    # ──────────────────────────────────────────────────────────────────────
    # MAIN WORKER
    # ──────────────────────────────────────────────────────────────────────

    def run(self):

        s = self._s
        s["running"] = True

        # ──────────────────────────────────────────────────────────────
        # MediaPipe
        # ──────────────────────────────────────────────────────────────

        mp_hands = mp.solutions.hands
        mp_drawing = mp.solutions.drawing_utils
        mp_styles = mp.solutions.drawing_styles

        hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.5,
        )

        # ──────────────────────────────────────────────────────────────
        # Camera
        # ──────────────────────────────────────────────────────────────

        current_idx = s["cam_idx"]

        cap = self._open_camera(
            current_idx
        )

        if cap.isOpened():

            self.status_sig.emit(
                f"✅ Camera {current_idx} ready",
                "#22c55e"
            )

        else:

            self.status_sig.emit(
                f"❌ Camera {current_idx} not found",
                "#ef4444"
            )

        # ──────────────────────────────────────────────────────────────
        # Tracking state
        # ──────────────────────────────────────────────────────────────

        last_pen_point = None
        was_pinching = False

        undo_cooldown = 0
        button_cooldown = 0

        # ──────────────────────────────────────────────────────────────
        # Helpers
        # ──────────────────────────────────────────────────────────────

        def landmark_px(landmark, width, height):

            return np.array(
                [
                    landmark.x * width,
                    landmark.y * height,
                ],
                dtype=np.float32
            )

        def distance(a, b):

            return float(
                np.linalg.norm(a - b)
            )

        # ──────────────────────────────────────────────────────────────
        # CAMERA LOOP
        # ──────────────────────────────────────────────────────────────

        while s["running"]:

            # ---------------------------------------------------------
            # Hot swap camera
            # ---------------------------------------------------------

            if s["cam_idx"] != current_idx:

                try:
                    cap.release()
                except Exception:
                    pass

                current_idx = s["cam_idx"]

                cap = self._open_camera(
                    current_idx
                )

                last_pen_point = None
                was_pinching = False

                if cap.isOpened():

                    self.status_sig.emit(
                        f"✅ Camera {current_idx} ready",
                        "#22c55e"
                    )

                else:

                    self.status_sig.emit(
                        f"❌ Camera {current_idx} not found",
                        "#ef4444"
                    )

            # ---------------------------------------------------------
            # Camera unavailable
            # ---------------------------------------------------------

            if not cap.isOpened():

                self.status_sig.emit(
                    "⚠ Camera unavailable",
                    "#f59e0b"
                )

                time.sleep(0.3)
                continue

            # ---------------------------------------------------------
            # Read frame
            # ---------------------------------------------------------

            ret, frame = cap.read()

            if not ret or frame is None:

                self.status_sig.emit(
                    "⚠ Frame grab failed",
                    "#f59e0b"
                )

                time.sleep(0.05)
                continue

            # Mirror webcam
            frame = cv2.flip(
                frame,
                1
            )

            h, w = frame.shape[:2]

            # Camera -> canvas scaling
            sx = SKETCH_CAM_W / max(1, w)
            sy = SKETCH_CAM_H / max(1, h)

            # ---------------------------------------------------------
            # Cooldowns
            # ---------------------------------------------------------

            if undo_cooldown > 0:
                undo_cooldown -= 1

            if button_cooldown > 0:
                button_cooldown -= 1

            # ---------------------------------------------------------
            # MediaPipe
            # ---------------------------------------------------------

            rgb = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB
            )

            rgb.flags.writeable = False

            results = hands.process(
                rgb
            )

            rgb.flags.writeable = True

            pen_point = None
            is_pinching = False

            # ---------------------------------------------------------
            # Hand detected
            # ---------------------------------------------------------

            if results.multi_hand_landmarks:

                hand_landmarks = (
                    results.multi_hand_landmarks[0]
                )

                landmarks = (
                    hand_landmarks.landmark
                )

                # Draw hand skeleton if enabled
                if s.get(
                    "show_landmarks",
                    True
                ):

                    mp_drawing.draw_landmarks(
                        frame,
                        hand_landmarks,
                        mp_hands.HAND_CONNECTIONS,
                        mp_styles.get_default_hand_landmarks_style(),
                        mp_styles.get_default_hand_connections_style(),
                    )

                # -----------------------------------------------------
                # Important landmarks
                #
                # 0 = wrist
                # 4 = thumb tip
                # 8 = index tip
                # 9 = middle MCP
                # -----------------------------------------------------

                wrist = landmark_px(
                    landmarks[0],
                    w,
                    h
                )

                middle_mcp = landmark_px(
                    landmarks[9],
                    w,
                    h
                )

                thumb_tip = landmark_px(
                    landmarks[4],
                    w,
                    h
                )

                index_tip = landmark_px(
                    landmarks[8],
                    w,
                    h
                )

                # -----------------------------------------------------
                # Pinch ratio
                # -----------------------------------------------------

                palm_size = (
                    distance(
                        middle_mcp,
                        wrist
                    )
                    or 1.0
                )

                pinch_distance = distance(
                    thumb_tip,
                    index_tip
                )

                pinch_ratio = (
                    pinch_distance /
                    palm_size
                )

                threshold = float(
                    s.get(
                        "pinch_threshold",
                        SKETCH_PINCH_THRESHOLD
                    )
                )

                is_pinching = (
                    pinch_ratio < threshold
                )

                # -----------------------------------------------------
                # Pen point
                # -----------------------------------------------------

                raw_point = (
                    thumb_tip +
                    index_tip
                ) / 2.0

                # -----------------------------------------------------
                # Smoothing
                # -----------------------------------------------------

                smoothing = float(
                    s.get(
                        "smoothing",
                        SKETCH_SMOOTHING
                    )
                )

                smoothing = max(
                    0.0,
                    min(0.95, smoothing)
                )

                alpha = 1.0 - smoothing

                if last_pen_point is None:

                    last_pen_point = raw_point

                else:

                    last_pen_point = (
                        alpha * raw_point
                        +
                        (1.0 - alpha) *
                        last_pen_point
                    )

                pen_point = (
                    int(last_pen_point[0]),
                    int(last_pen_point[1]),
                )

                # -----------------------------------------------------
                # Visual pinch feedback
                # -----------------------------------------------------

                feedback_color = (
                    (0, 255, 0)
                    if is_pinching
                    else
                    (180, 180, 180)
                )

                thumb_xy = (
                    int(thumb_tip[0]),
                    int(thumb_tip[1]),
                )

                index_xy = (
                    int(index_tip[0]),
                    int(index_tip[1]),
                )

                cv2.circle(
                    frame,
                    thumb_xy,
                    8,
                    feedback_color,
                    -1
                )

                cv2.circle(
                    frame,
                    index_xy,
                    8,
                    feedback_color,
                    -1
                )

                cv2.line(
                    frame,
                    thumb_xy,
                    index_xy,
                    feedback_color,
                    2
                )

                cv2.circle(
                    frame,
                    pen_point,
                    6,
                    (255, 255, 255),
                    -1
                )

                # Pinch value
                cv2.putText(
                    frame,
                    f"Pinch: {pinch_ratio:.2f}",
                    (20, h - 45),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (220, 220, 220),
                    1
                )

            else:

                last_pen_point = None
                was_pinching = False

            # ---------------------------------------------------------
            # On-camera buttons
            # ---------------------------------------------------------

            if (
                pen_point is not None
                and is_pinching
                and pen_point[1] <= 90
            ):

                if button_cooldown == 0:

                    px = pen_point[0]
                    py = pen_point[1]

                    # CLEAR
                    if 30 <= px <= 160:

                        s["cmd"] = "clear"

                        button_cooldown = (
                            SKETCH_BUTTON_COOLDOWN
                        )

                    # UNDO
                    elif (
                        190 <= px <= 320
                        and undo_cooldown == 0
                    ):

                        s["cmd"] = "undo"

                        undo_cooldown = (
                            SKETCH_UNDO_COOLDOWN
                        )

                        button_cooldown = (
                            SKETCH_BUTTON_COOLDOWN
                        )

                    # COLORS
                    elif 400 <= px <= 720:

                        for i in range(4):

                            xc = 400 + i * 80

                            distance_sq = (
                                (xc - px) ** 2
                                +
                                (47 - py) ** 2
                            )

                            if distance_sq <= 32 ** 2:

                                s["color_idx"] = i

                                self.color_sig.emit(
                                    i
                                )

                                button_cooldown = (
                                    SKETCH_BUTTON_COOLDOWN
                                )

                                break

                was_pinching = False
                last_pen_point = None

                self.status_sig.emit(
                    "Pinch over button row",
                    "#94a3b8"
                )

            # ---------------------------------------------------------
            # DRAW
            # ---------------------------------------------------------

            elif (
                pen_point is not None
                and is_pinching
            ):

                canvas_x = int(
                    pen_point[0] * sx
                )

                canvas_y = int(
                    pen_point[1] * sy
                )

                canvas_x = max(
                    0,
                    min(
                        SKETCH_CAM_W - 1,
                        canvas_x
                    )
                )

                canvas_y = max(
                    0,
                    min(
                        SKETCH_CAM_H - 1,
                        canvas_y
                    )
                )

                color_idx = int(
                    s.get(
                        "color_idx",
                        0
                    )
                )

                point_lists = s[
                    "point_lists"
                ]

                undo_stack = s[
                    "undo_stack"
                ]

                lock = s[
                    "lock"
                ]

                with lock:

                    pts = point_lists[
                        color_idx
                    ]

                    # Start a new stroke
                    if not was_pinching:

                        pts.append(
                            deque(
                                maxlen=4096
                            )
                        )

                        undo_stack.append(
                            {
                                "list": pts,
                                "index": (
                                    len(pts) - 1
                                ),
                            }
                        )

                    pts[-1].appendleft(
                        (
                            canvas_x,
                            canvas_y
                        )
                    )

                was_pinching = True

                s[
                    "needs_redraw"
                ] = True

                self.status_sig.emit(
                    "🖊 Drawing",
                    "#22c55e"
                )

            # ---------------------------------------------------------
            # Hand visible but not pinching
            # ---------------------------------------------------------

            elif pen_point is not None:

                was_pinching = False

                self.status_sig.emit(
                    "✋ Hand detected — pinch to draw",
                    "#64748b"
                )

            # ---------------------------------------------------------
            # No hand
            # ---------------------------------------------------------

            else:

                was_pinching = False

                self.status_sig.emit(
                    "No hand detected",
                    "#64748b"
                )

            # ---------------------------------------------------------
            # Camera UI
            # ---------------------------------------------------------

            # CLEAR
            cv2.rectangle(
                frame,
                (30, 15),
                (160, 80),
                (50, 50, 50),
                -1
            )

            cv2.putText(
                frame,
                "CLEAR",
                (50, 55),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2
            )

            # UNDO
            cv2.rectangle(
                frame,
                (190, 15),
                (320, 80),
                (50, 50, 50),
                -1
            )

            cv2.putText(
                frame,
                "UNDO",
                (215, 55),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2
            )

            # COLORS
            color_idx = int(
                s.get(
                    "color_idx",
                    0
                )
            )

            for i, color in enumerate(
                SKETCH_COLORS_BGR
            ):

                xc = 400 + i * 80

                cv2.circle(
                    frame,
                    (xc, 47),
                    28,
                    color,
                    -1
                )

                if i == color_idx:

                    cv2.circle(
                        frame,
                        (xc, 47),
                        32,
                        (255, 255, 255),
                        3
                    )

            # GUIDE BOX
            mx = int(
                w * SKETCH_GUIDE_MARGIN
            )

            my = int(
                h * SKETCH_GUIDE_MARGIN
            )

            cv2.rectangle(
                frame,
                (
                    mx,
                    my + 90
                ),
                (
                    w - mx,
                    h - my
                ),
                (0, 255, 0),
                2
            )

            cv2.putText(
                frame,
                "Place paper inside this box",
                (
                    mx,
                    my + 84
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2
            )

            # ---------------------------------------------------------
            # Debug image
            # ---------------------------------------------------------

            debug = np.zeros(
                (
                    h,
                    w,
                    3
                ),
                dtype=np.uint8
            )

            if results.multi_hand_landmarks:

                for hand in (
                    results.multi_hand_landmarks
                ):

                    landmarks_for_debug = (
                        hand.landmark
                    )

                    # Draw connections
                    for connection in (
                        mp_hands.HAND_CONNECTIONS
                    ):

                        start_idx = connection[0]
                        end_idx = connection[1]

                        p1 = (
                            landmarks_for_debug[
                                start_idx
                            ]
                        )

                        p2 = (
                            landmarks_for_debug[
                                end_idx
                            ]
                        )

                        x1 = int(
                            p1.x * w
                        )

                        y1 = int(
                            p1.y * h
                        )

                        x2 = int(
                            p2.x * w
                        )

                        y2 = int(
                            p2.y * h
                        )

                        cv2.line(
                            debug,
                            (x1, y1),
                            (x2, y2),
                            (100, 180, 255),
                            2
                        )

                    # Draw landmarks
                    for landmark in (
                        landmarks_for_debug
                    ):

                        x = int(
                            landmark.x * w
                        )

                        y = int(
                            landmark.y * h
                        )

                        if (
                            0 <= x < w
                            and
                            0 <= y < h
                        ):

                            cv2.circle(
                                debug,
                                (x, y),
                                4,
                                (255, 255, 255),
                                -1
                            )

            # ---------------------------------------------------------
            # Send frames
            # ---------------------------------------------------------

            self.frame_ready.emit(
                frame.copy(),
                debug.copy()
            )

        # ──────────────────────────────────────────────────────────────
        # Shutdown
        # ──────────────────────────────────────────────────────────────

        try:
            hands.close()
        except Exception:
            pass

        try:
            cap.release()
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# SKETCH SECTION
# ──────────────────────────────────────────────────────────────────────────────

class SketchSection(QWidget):

    def __init__(self, parent=None):

        super().__init__(parent)

        # Worker
        self._cam_worker = None

        # Poll timer
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(16)
        self._poll_timer.timeout.connect(
            self._on_poll
        )

        # Shared state
        self._state = {
            "running": False,
            "cam_idx": 0,
            "color_idx": 0,
            "brush": 3,

            "point_lists": [
                [],
                [],
                [],
                [],
            ],

            "undo_stack": [],

            "lock": __import__(
                "threading"
            ).Lock(),

            "needs_redraw": False,
            "cmd": None,

            # MediaPipe
            "pinch_threshold":
                SKETCH_PINCH_THRESHOLD,

            "smoothing":
                SKETCH_SMOOTHING,

            "show_landmarks":
                True,
        }

        self._canvas_img = None

        self._build_ui()

    # =========================================================================
    # UI
    # =========================================================================

    def _build_ui(self):

        root = QVBoxLayout(self)

        root.setContentsMargins(
            0,
            0,
            0,
            0
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

        tb = QHBoxLayout(toolbar)

        tb.setContentsMargins(
            10,
            6,
            10,
            6
        )

        tb.setSpacing(8)

        lbl = QLabel(
            "✏️  Sketch Studio"
        )

        lbl.setStyleSheet(
            "font-size:16px;"
            "font-weight:bold;"
            "color:#e0e0ff;"
        )

        tb.addWidget(lbl)

        self._start_btn = QPushButton(
            "▶ Start Camera"
        )

        self._start_btn.setObjectName(
            "action_btn"
        )

        self._start_btn.setFixedHeight(
            34
        )

        self._start_btn.clicked.connect(
            self._start
        )

        tb.addWidget(
            self._start_btn
        )

        self._stop_btn = QPushButton(
            "⏹ Stop"
        )

        self._stop_btn.setObjectName(
            "danger_btn"
        )

        self._stop_btn.setFixedHeight(
            34
        )

        self._stop_btn.setEnabled(
            False
        )

        self._stop_btn.clicked.connect(
            self._stop
        )

        tb.addWidget(
            self._stop_btn
        )

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

        self._status_lbl = QLabel(
            "Not started"
        )

        self._status_lbl.setStyleSheet(
            "color:#64748b;"
            "font-size:11px;"
        )

        tb.addWidget(
            self._status_lbl
        )

        tb.addStretch()

        root.addWidget(toolbar)

        # ──────────────────────────────────────────────────────────────
        # Body
        # ──────────────────────────────────────────────────────────────

        body = QWidget()

        body_lay = QHBoxLayout(body)

        body_lay.setContentsMargins(
            0,
            0,
            0,
            0
        )

        body_lay.setSpacing(0)

        # ──────────────────────────────────────────────────────────────
        # Sidebar
        # ──────────────────────────────────────────────────────────────

        sidebar = QScrollArea()

        sidebar.setFixedWidth(
            200
        )

        sidebar.setWidgetResizable(
            True
        )

        sidebar.setStyleSheet(
            "QScrollArea{"
            "background:#0f172a;"
            "border:none;"
            "}"
            "QWidget{"
            "background:#0f172a;"
            "}"
        )

        side_inner = QWidget()

        side_inner.setStyleSheet(
            "background:#0f172a;"
        )

        side_lay = QVBoxLayout(
            side_inner
        )

        side_lay.setContentsMargins(
            8,
            10,
            8,
            10
        )

        side_lay.setSpacing(8)

        # Camera index
        cam_lbl = QLabel(
            "CAMERA INDEX"
        )

        cam_lbl.setStyleSheet(
            "color:#475569;"
            "font-size:10px;"
            "font-weight:bold;"
        )

        side_lay.addWidget(
            cam_lbl
        )

        cam_row = QWidget()

        cam_row_lay = QHBoxLayout(
            cam_row
        )

        cam_row_lay.setContentsMargins(
            0,
            0,
            0,
            0
        )

        self._cam_entry = QLineEdit(
            "0"
        )

        self._cam_entry.setFixedWidth(
            44
        )

        cam_apply = QPushButton(
            "Apply"
        )

        cam_apply.setObjectName(
            "action_btn"
        )

        cam_apply.setFixedHeight(
            26
        )

        cam_apply.clicked.connect(
            self._apply_cam
        )

        cam_row_lay.addWidget(
            self._cam_entry
        )

        cam_row_lay.addWidget(
            cam_apply
        )

        cam_row_lay.addStretch()

        side_lay.addWidget(
            cam_row
        )

        # Separator
        sep1 = QFrame()

        sep1.setFrameShape(
            QFrame.Shape.HLine
        )

        sep1.setStyleSheet(
            "color:#334155;"
        )

        side_lay.addWidget(
            sep1
        )

        # Draw color
        color_lbl = QLabel(
            "DRAW COLOR"
        )

        color_lbl.setStyleSheet(
            "color:#94a3b8;"
            "font-size:11px;"
            "font-weight:bold;"
        )

        side_lay.addWidget(
            color_lbl
        )

        color_row = QWidget()

        cr_lay = QHBoxLayout(
            color_row
        )

        cr_lay.setContentsMargins(
            0,
            0,
            0,
            0
        )

        cr_lay.setSpacing(4)

        self._color_btns = []

        for i, (
            hex_col,
            name
        ) in enumerate(
            zip(
                SKETCH_COLORS_HEX,
                SKETCH_COLOR_NAMES
            )
        ):

            btn = QPushButton()

            btn.setFixedSize(
                28,
                28
            )

            btn.setToolTip(
                name
            )

            btn.setStyleSheet(
                f"background:{hex_col};"
                "border-radius:14px;"
                "border:2px solid #64748b;"
            )

            btn.clicked.connect(
                lambda _, idx=i:
                self._set_color(idx)
            )

            cr_lay.addWidget(
                btn
            )

            self._color_btns.append(
                btn
            )

        side_lay.addWidget(
            color_row
        )

        self._update_color_ui()

        # Brush
        brush_lbl = QLabel(
            "BRUSH SIZE"
        )

        brush_lbl.setStyleSheet(
            "color:#94a3b8;"
            "font-size:11px;"
            "font-weight:bold;"
        )

        side_lay.addWidget(
            brush_lbl
        )

        brush_row = QWidget()

        br_lay = QHBoxLayout(
            brush_row
        )

        br_lay.setContentsMargins(
            0,
            0,
            0,
            0
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

        self._brush_lbl = QLabel(
            "3"
        )

        self._brush_lbl.setFixedWidth(
            20
        )

        self._brush_slider.valueChanged.connect(
            self._on_brush_changed
        )

        br_lay.addWidget(
            self._brush_slider
        )

        br_lay.addWidget(
            self._brush_lbl
        )

        side_lay.addWidget(
            brush_row
        )

        # Separator
        sep2 = QFrame()

        sep2.setFrameShape(
            QFrame.Shape.HLine
        )

        sep2.setStyleSheet(
            "color:#334155;"
        )

        side_lay.addWidget(
            sep2
        )

        # ──────────────────────────────────────────────────────────────
        # Hand tracking settings
        # ──────────────────────────────────────────────────────────────

        tracking_lbl = QLabel(
            "HAND TRACKING"
        )

        tracking_lbl.setStyleSheet(
            "color:#94a3b8;"
            "font-size:11px;"
            "font-weight:bold;"
        )

        side_lay.addWidget(
            tracking_lbl
        )

        desc = QLabel(
            "Pinch thumb + index finger "
            "to draw."
        )

        desc.setStyleSheet(
            "color:#64748b;"
            "font-size:9px;"
        )

        desc.setWordWrap(
            True
        )

        side_lay.addWidget(
            desc
        )

        # Pinch threshold
        pinch_row = QWidget()

        pinch_layout = QHBoxLayout(
            pinch_row
        )

        pinch_layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        pinch_name = QLabel(
            "Pinch"
        )

        pinch_name.setFixedWidth(
            40
        )

        pinch_name.setStyleSheet(
            "color:#64748b;"
            "font-size:10px;"
        )

        self._pinch_lbl = QLabel(
            f"{SKETCH_PINCH_THRESHOLD:.2f}"
        )

        self._pinch_lbl.setFixedWidth(
            30
        )

        self._pinch_lbl.setStyleSheet(
            "color:#cbd5e1;"
            "font-size:10px;"
        )

        self._pinch_slider = QSlider(
            Qt.Orientation.Horizontal
        )

        self._pinch_slider.setRange(
            15,
            65
        )

        self._pinch_slider.setValue(
            int(
                SKETCH_PINCH_THRESHOLD * 100
            )
        )

        self._pinch_slider.valueChanged.connect(
            self._on_pinch_changed
        )

        pinch_layout.addWidget(
            pinch_name
        )

        pinch_layout.addWidget(
            self._pinch_slider
        )

        pinch_layout.addWidget(
            self._pinch_lbl
        )

        side_lay.addWidget(
            pinch_row
        )

        # Smoothing
        smooth_row = QWidget()

        smooth_layout = QHBoxLayout(
            smooth_row
        )

        smooth_layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        smooth_name = QLabel(
            "Smooth"
        )

        smooth_name.setFixedWidth(
            40
        )

        smooth_name.setStyleSheet(
            "color:#64748b;"
            "font-size:10px;"
        )

        self._smooth_lbl = QLabel(
            f"{SKETCH_SMOOTHING:.2f}"
        )

        self._smooth_lbl.setFixedWidth(
            30
        )

        self._smooth_lbl.setStyleSheet(
            "color:#cbd5e1;"
            "font-size:10px;"
        )

        self._smooth_slider = QSlider(
            Qt.Orientation.Horizontal
        )

        self._smooth_slider.setRange(
            0,
            80
        )

        self._smooth_slider.setValue(
            int(
                SKETCH_SMOOTHING * 100
            )
        )

        self._smooth_slider.valueChanged.connect(
            self._on_smoothing_changed
        )

        smooth_layout.addWidget(
            smooth_name
        )

        smooth_layout.addWidget(
            self._smooth_slider
        )

        smooth_layout.addWidget(
            self._smooth_lbl
        )

        side_lay.addWidget(
            smooth_row
        )

        # Skeleton toggle
        self._landmarks_btn = QPushButton(
            "✓  Show Hand Skeleton"
        )

        self._landmarks_btn.setCheckable(
            True
        )

        self._landmarks_btn.setChecked(
            True
        )

        self._landmarks_btn.setObjectName(
            "action_btn"
        )

        self._landmarks_btn.clicked.connect(
            self._toggle_landmarks
        )

        side_lay.addWidget(
            self._landmarks_btn
        )

        # Info
        info_lbl = QLabel(
            "Pinch thumb + index to draw.\n"
            "Move to CLEAR / UNDO / colors\n"
            "at the top of the camera feed."
        )

        info_lbl.setStyleSheet(
            "color:#334155;"
            "font-size:9px;"
        )

        info_lbl.setWordWrap(
            True
        )

        info_lbl.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        side_lay.addWidget(
            info_lbl
        )

        side_lay.addStretch()

        sidebar.setWidget(
            side_inner
        )

        body_lay.addWidget(
            sidebar
        )

        # ──────────────────────────────────────────────────────────────
        # Camera / Ink split
        # ──────────────────────────────────────────────────────────────

        v_splitter = QSplitter(
            Qt.Orientation.Vertical
        )

        v_splitter.setHandleWidth(
            6
        )

        h_splitter = QSplitter(
            Qt.Orientation.Horizontal
        )

        h_splitter.setHandleWidth(
            6
        )

        # Camera
        cam_frame = QFrame()

        cam_frame.setStyleSheet(
            "background:#1e293b;"
            "border-radius:6px;"
        )

        cam_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )

        cam_v = QVBoxLayout(
            cam_frame
        )

        cam_v.setContentsMargins(
            4,
            4,
            4,
            4
        )

        cam_v.setSpacing(4)

        cam_hdr = QLabel(
            "📷  Camera Feed  "
            "(drag handle to resize →)"
        )

        cam_hdr.setStyleSheet(
            "color:#94a3b8;"
            "font-size:10px;"
        )

        cam_v.addWidget(
            cam_hdr
        )

        self._cam_lbl = QLabel()

        self._cam_lbl.setMinimumSize(
            200,
            150
        )

        self._cam_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )

        self._cam_lbl.setStyleSheet(
            "background:#0f172a;"
            "border-radius:4px;"
        )

        self._cam_lbl.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self._cam_lbl.setText(
            "Camera not started"
        )

        self._cam_lbl.setScaledContents(
            False
        )

        cam_v.addWidget(
            self._cam_lbl,
            stretch=1
        )

        # Ink
        ink_frame = QFrame()

        ink_frame.setStyleSheet(
            "background:#1e293b;"
            "border-radius:6px;"
        )

        ink_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )

        ink_v = QVBoxLayout(
            ink_frame
        )

        ink_v.setContentsMargins(
            4,
            4,
            4,
            4
        )

        ink_v.setSpacing(4)

        ink_hdr = QLabel(
            "🖊  Ink Canvas"
        )

        ink_hdr.setStyleSheet(
            "color:#94a3b8;"
            "font-size:10px;"
        )

        ink_v.addWidget(
            ink_hdr
        )

        self._ink_lbl = QLabel()

        self._ink_lbl.setMinimumSize(
            150,
            150
        )

        self._ink_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )

        self._ink_lbl.setStyleSheet(
            "background:#ffffff;"
            "border-radius:4px;"
        )

        self._ink_lbl.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self._ink_lbl.setScaledContents(
            False
        )

        ink_v.addWidget(
            self._ink_lbl,
            stretch=1
        )

        h_splitter.addWidget(
            cam_frame
        )

        h_splitter.addWidget(
            ink_frame
        )

        h_splitter.setStretchFactor(
            0,
            6
        )

        h_splitter.setStretchFactor(
            1,
            4
        )

        # ──────────────────────────────────────────────────────────────
        # Hand debug
        # ──────────────────────────────────────────────────────────────

        debug_frame = QFrame()

        debug_frame.setStyleSheet(
            "background:#1e293b;"
            "border-radius:6px;"
        )

        debug_v = QVBoxLayout(
            debug_frame
        )

        debug_v.setContentsMargins(
            4,
            4,
            4,
            4
        )

        debug_v.setSpacing(2)

        debug_hdr = QLabel(
            "🖐  Hand Tracking Debug  "
            "(drag handle ↑ to expand)"
        )

        debug_hdr.setStyleSheet(
            "color:#64748b;"
            "font-size:10px;"
        )

        debug_v.addWidget(
            debug_hdr
        )

        self._mask_lbl = QLabel()

        self._mask_lbl.setMinimumHeight(
            30
        )

        self._mask_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )

        self._mask_lbl.setStyleSheet(
            "background:#0f172a;"
            "border-radius:4px;"
        )

        self._mask_lbl.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self._mask_lbl.setScaledContents(
            False
        )

        debug_v.addWidget(
            self._mask_lbl,
            stretch=1
        )

        v_splitter.addWidget(
            h_splitter
        )

        v_splitter.addWidget(
            debug_frame
        )

        v_splitter.setStretchFactor(
            0,
            10
        )

        v_splitter.setStretchFactor(
            1,
            1
        )

        body_lay.addWidget(
            v_splitter,
            stretch=1
        )

        root.addWidget(
            body,
            stretch=1
        )

    # =========================================================================
    # FRAME CONVERSION
    # =========================================================================

    def _np_to_qpixmap(
        self,
        arr,
        width: int,
        height: int,
    ) -> QPixmap:

        if arr is None:
            return QPixmap()

        resized = cv2.resize(
            arr,
            (
                max(1, width),
                max(1, height),
            )
        )

        if len(
            resized.shape
        ) == 2:

            resized = cv2.cvtColor(
                resized,
                cv2.COLOR_GRAY2RGB
            )

        else:

            resized = cv2.cvtColor(
                resized,
                cv2.COLOR_BGR2RGB
            )

        image = QImage(
            resized.data,
            resized.shape[1],
            resized.shape[0],
            resized.strides[0],
            QImage.Format.Format_RGB888,
        ).copy()

        return QPixmap.fromImage(
            image
        )

    # =========================================================================
    # START
    # =========================================================================

    def _start(self):

        if (
            self._cam_worker
            and self._cam_worker.isRunning()
        ):
            return

        self._state["running"] = True

        self._state[
            "point_lists"
        ] = [
            [],
            [],
            [],
            [],
        ]

        self._state[
            "undo_stack"
        ] = []

        self._state[
            "needs_redraw"
        ] = False

        self._state[
            "cmd"
        ] = None

        self._canvas_img = None

        self._cam_worker = (
            _SketchCamWorker(
                self._state
            )
        )

        self._cam_worker.frame_ready.connect(
            self._on_frame
        )

        self._cam_worker.status_sig.connect(
            self._on_worker_status
        )

        self._cam_worker.color_sig.connect(
            self._set_color
        )

        self._cam_worker.start()

        self._poll_timer.start()

        self._start_btn.setEnabled(
            False
        )

        self._stop_btn.setEnabled(
            True
        )

        self._status_lbl.setText(
            "⏳ Starting camera…"
        )

    # =========================================================================
    # STATUS
    # =========================================================================

    def _on_worker_status(
        self,
        message,
        color,
    ):

        self._status_lbl.setText(
            message
        )

        self._status_lbl.setStyleSheet(
            f"color:{color};"
            "font-size:11px;"
        )

    # =========================================================================
    # STOP
    # =========================================================================

    def _stop(self):

        self._state[
            "running"
        ] = False

        self._poll_timer.stop()

        if self._cam_worker:

            if self._cam_worker.isRunning():

                self._cam_worker.wait(
                    3000
                )

            self._cam_worker = None

        self._start_btn.setEnabled(
            True
        )

        self._stop_btn.setEnabled(
            False
        )

        self._status_lbl.setText(
            "Stopped"
        )

        self._status_lbl.setStyleSheet(
            "color:#64748b;"
            "font-size:11px;"
        )

        self._cam_lbl.clear()

        self._cam_lbl.setText(
            "Camera not started"
        )

        self._mask_lbl.clear()

        self._canvas_img = None

    # =========================================================================
    # FRAME
    # =========================================================================

    def _on_frame(
        self,
        frame,
        debug,
    ):

        cw = max(
            self._cam_lbl.width(),
            320
        )

        ch = max(
            self._cam_lbl.height(),
            240
        )

        self._cam_lbl.setPixmap(
            self._np_to_qpixmap(
                frame,
                cw,
                ch
            )
        )

        dw = max(
            self._mask_lbl.width(),
            200
        )

        dh = max(
            self._mask_lbl.height(),
            60
        )

        self._mask_lbl.setPixmap(
            self._np_to_qpixmap(
                debug,
                dw,
                dh
            )
        )

    # =========================================================================
    # POLL / REDRAW
    # =========================================================================

    def _on_poll(self):

        s = self._state

        command = s.get(
            "cmd"
        )

        if command == "clear":

            self._clear()

            s["cmd"] = None

        elif command == "undo":

            self._undo()

            s["cmd"] = None

        if not s.get(
            "needs_redraw"
        ):
            return

        s["needs_redraw"] = False

        with s["lock"]:

            image = np.ones(
                (
                    SKETCH_CAM_H,
                    SKETCH_CAM_W,
                    3,
                ),
                dtype=np.uint8,
            ) * 255

            for pts, bgr in zip(
                s["point_lists"],
                SKETCH_COLORS_BGR,
            ):

                for stroke in pts:

                    points = list(
                        stroke
                    )

                    if len(points) == 0:
                        continue

                    if len(points) == 1:

                        cv2.circle(
                            image,
                            points[0],
                            max(
                                1,
                                int(
                                    s["brush"]
                                ) // 2
                            ),
                            bgr,
                            -1,
                        )

                        continue

                    for i in range(
                        1,
                        len(points)
                    ):

                        p1 = points[
                            i - 1
                        ]

                        p2 = points[
                            i
                        ]

                        if (
                            p1 is None
                            or p2 is None
                        ):
                            continue

                        cv2.line(
                            image,
                            p1,
                            p2,
                            bgr,
                            int(
                                s["brush"]
                            ),
                            lineType=cv2.LINE_AA,
                        )

            self._canvas_img = image.copy()

        iw = max(
            self._ink_lbl.width(),
            320
        )

        ih = max(
            self._ink_lbl.height(),
            240
        )

        self._ink_lbl.setPixmap(
            self._np_to_qpixmap(
                self._canvas_img,
                iw,
                ih
            )
        )

    # =========================================================================
    # BRUSH
    # =========================================================================

    def _on_brush_changed(
        self,
        value,
    ):

        self._state[
            "brush"
        ] = int(value)

        self._brush_lbl.setText(
            str(int(value))
        )

    # =========================================================================
    # COLOR
    # =========================================================================

    def _update_color_ui(self):

        idx = self._state[
            "color_idx"
        ]

        for i, btn in enumerate(
            self._color_btns
        ):

            border = (
                "#ffffff"
                if i == idx
                else "#64748b"
            )

            width = (
                "3"
                if i == idx
                else "2"
            )

            btn.setStyleSheet(
                f"background:{SKETCH_COLORS_HEX[i]};"
                f"border-radius:14px;"
                f"border:{width}px solid {border};"
            )

    def _set_color(
        self,
        idx: int,
    ):

        if not (
            0 <= idx
            < len(
                SKETCH_COLORS_HEX
            )
        ):
            return

        self._state[
            "color_idx"
        ] = idx

        self._update_color_ui()

    # =========================================================================
    # PINCH
    # =========================================================================

    def _on_pinch_changed(
        self,
        value,
    ):

        threshold = (
            int(value) / 100.0
        )

        self._state[
            "pinch_threshold"
        ] = threshold

        self._pinch_lbl.setText(
            f"{threshold:.2f}"
        )

    # =========================================================================
    # SMOOTHING
    # =========================================================================

    def _on_smoothing_changed(
        self,
        value,
    ):

        smoothing = (
            int(value) / 100.0
        )

        self._state[
            "smoothing"
        ] = smoothing

        self._smooth_lbl.setText(
            f"{smoothing:.2f}"
        )

    # =========================================================================
    # LANDMARKS
    # =========================================================================

    def _toggle_landmarks(self):

        enabled = (
            self._landmarks_btn.isChecked()
        )

        self._state[
            "show_landmarks"
        ] = enabled

        self._landmarks_btn.setText(
            "✓  Show Hand Skeleton"
            if enabled
            else
            "  Show Hand Skeleton"
        )

    # =========================================================================
    # UNDO
    # =========================================================================

    def _undo(self):

        s = self._state

        with s["lock"]:

            while s["undo_stack"]:

                entry = (
                    s["undo_stack"].pop()
                )

                pts = entry[
                    "list"
                ]

                idx = entry[
                    "index"
                ]

                if (
                    idx < len(pts)
                    and len(
                        pts[idx]
                    ) > 0
                ):

                    pts[idx].clear()
                    break

        s[
            "needs_redraw"
        ] = True

    # =========================================================================
    # CLEAR
    # =========================================================================

    def _clear(self):

        s = self._state

        with s["lock"]:

            for pts in (
                s["point_lists"]
            ):
                pts.clear()

            s[
                "undo_stack"
            ].clear()

        s[
            "needs_redraw"
        ] = True

    # =========================================================================
    # CAMERA INDEX
    # =========================================================================

    def _apply_cam(self):

        try:

            index = int(
                self._cam_entry.text()
            )

            self._state[
                "cam_idx"
            ] = index

            self._status_lbl.setText(
                f"⏳ Switching to camera "
                f"{index}…"
            )

            self._status_lbl.setStyleSheet(
                "color:#f59e0b;"
                "font-size:11px;"
            )

        except ValueError:

            self._status_lbl.setText(
                "❌ Invalid camera index"
            )

            self._status_lbl.setStyleSheet(
                "color:#ef4444;"
                "font-size:11px;"
            )

    # =========================================================================
    # SAVE
    # =========================================================================

    def _save(self):

        if self._canvas_img is None:

            qmsg_warn(
                self,
                "Nothing to save",
                "Start the camera and draw something first.",
            )

            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Sketch",
            str(
                SAVED_OUTPUTS_DIR
                / "sketch_save.png"
            ),
            "PNG Image (*.png)",
        )

        if not path:
            return

        try:

            cv2.imwrite(
                path,
                self._canvas_img
            )

            qmsg_info(
                self,
                "Saved",
                f"Sketch saved to:\n{path}"
            )

        except Exception as e:

            qmsg_err(
                self,
                "Save failed",
                str(e)
            )

    # =========================================================================
    # SHUTDOWN
    # =========================================================================

    def shutdown(self):

        self._stop()