from pathlib import Path


# ─────────────────────────────────────────────
# BASE PATHS
# ─────────────────────────────────────────────

BASE_DIR = Path(__file__).parent

DOCUMENTS_DIR = BASE_DIR / "documents"
DOCUMENTS_DIR.mkdir(
    parents=True,
    exist_ok=True
)

SAVED_OUTPUTS_DIR = BASE_DIR / "saved_outputs"
SAVED_OUTPUTS_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ─────────────────────────────────────────────
# EXTERNAL SCRIPTS
# ─────────────────────────────────────────────

CANVAS_SCRIPT = BASE_DIR / "canvas.py"
SKETCH_SCRIPT = BASE_DIR / "sketch.py"
#PRESENTATION_SCRIPT = BASE_DIR / "presentation.py"
SUMMARIZE_SCRIPT = BASE_DIR / "summarize.py"


# ─────────────────────────────────────────────
# STREAMLIT
# ─────────────────────────────────────────────

STREAMLIT_PORT = 8501
STREAMLIT_URL = f"http://localhost:{STREAMLIT_PORT}"


# ─────────────────────────────────────────────
# CANVAS
# ─────────────────────────────────────────────

CANVAS_W = 6000
CANVAS_H = 5000


# ─────────────────────────────────────────────
# SKETCH / MEDIAPIPE
# ─────────────────────────────────────────────

SKETCH_COLORS_BGR = [
    (20, 20, 20),
    (0, 200, 0),
    (0, 0, 220),
    (220, 0, 0),
]

SKETCH_COLORS_HEX = [
    "#111111",
    "#00c853",
    "#f44336",
    "#2196f3",
]

SKETCH_COLOR_NAMES = [
    "Black",
    "Green",
    "Red",
    "Blue",
]

SKETCH_PINCH_THRESHOLD = 0.42
SKETCH_SMOOTHING = 0.35

SKETCH_UNDO_COOLDOWN = 20
SKETCH_BUTTON_COOLDOWN = 15

SKETCH_CAM_W = 1280
SKETCH_CAM_H = 720

SKETCH_GUIDE_MARGIN = 0.12