"""
AI OCR + Summarization pipeline
================================

Backend:
    Ollama + Qwen2.5-VL

Pipeline:
    Image/PDF
        ↓
    Convert to image
        ↓
    Base64
        ↓
    Ollama
        ↓
    Qwen2.5-VL
        ↓
    OCR text
        ↓
    Summary
        ↓
    last_ocr_result.json
        ↓
    slide_NNN_notes.txt

Importable API
--------------
from ocr_pipeline import (
    ocr_and_summarize,
    ocr_all_slides,
    read_last_output,
    read_last_ocr_result,
    ocr_last_output,
    load_slide_notes,
    OcrResult,
)

Examples
--------
ocr_and_summarize("slide.png")

ocr_and_summarize(
    "slide.png",
    slide_folder="documents/myfolder",
    slide_num=2,
)

ocr_and_summarize(numpy_bgr_array)

ocr_all_slides(
    slide_paths,
    slide_folder="documents/myfolder",
)

No Tesseract is required.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Union

import numpy as np


# =============================================================================
# CONFIG
# =============================================================================

_ROOT = Path(__file__).resolve().parent

_LAST_OUT_FILE = (
    _ROOT / "last_output.json"
)

_LAST_OCR_FILE = (
    _ROOT / "last_ocr_result.json"
)

_DOCS_DIR = (
    _ROOT / "documents"
)

# Ollama API
OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://localhost:11434/api/chat",
).strip()

# Your proposal/report model
OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5vl:3b",
).strip()

OLLAMA_TIMEOUT = int(
    os.getenv(
        "OLLAMA_TIMEOUT",
        "120",
    )
)

# Image settings
MAX_IMAGE_SIZE = 1600
JPEG_QUALITY = 85

# PDF settings
PDF_DPI = 150

# Prevent huge multi-page requests
MAX_PAGES_PER_REQUEST = 4


# =============================================================================
# RESULT
# =============================================================================

@dataclass
class OcrResult:
    raw_text: str
    summary: str
    notes_path: Optional[Path]
    model_used: str
    source: str
    pages: int = 1
    error: str = ""


# =============================================================================
# OLLAMA STATUS
# =============================================================================

def _ollama_available() -> bool:
    """
    Check whether the Ollama server is reachable.

    Ollama normally serves its local API on:
        http://localhost:11434
    """

    import socket

    try:

        with socket.create_connection(
            ("localhost", 11434),
            timeout=1,
        ):
            return True

    except OSError:

        return False


# =============================================================================
# OLLAMA REQUEST
# =============================================================================

def _call_ollama(
    prompt: str,
    images_b64: Optional[list[str]] = None,
    max_tokens: int = 800,
) -> str:
    """
    Send a prompt, optionally with images, to Ollama.

    Qwen2.5-VL receives images through the `images`
    field of the user message.
    """

    import requests

    payload = {
        "model": OLLAMA_MODEL,

        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],

        "stream": False,

        "options": {
            "temperature": 0.2,
            "num_predict": max_tokens,
        },
    }

    # Vision input
    if images_b64:

        payload["messages"][0][
            "images"
        ] = images_b64

    try:

        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=OLLAMA_TIMEOUT,
        )

        response.raise_for_status()

        data = response.json()

        # /api/chat format
        message = data.get(
            "message",
            {},
        )

        text = message.get(
            "content",
            "",
        )

        # Fallback in case an older response format is returned.
        if not text:

            text = data.get(
                "response",
                "",
            )

        text = text.strip()

        return _clean_model_text(
            text
        )

    except requests.exceptions.ConnectionError:

        return (
            "[Ollama error: Could not connect "
            "to Ollama. Start Ollama first.]"
        )

    except requests.exceptions.Timeout:

        return (
            "[Ollama error: Request timed out.]"
        )

    except Exception as e:

        return (
            f"[Ollama error: {e}]"
        )


# =============================================================================
# TEXT CLEANING
# =============================================================================

def _clean_model_text(
    text: str,
) -> str:
    """
    Remove unnecessary Markdown formatting.
    """

    if not text:
        return ""

    text = text.strip()

    # Headings
    text = re.sub(
        r"^\s*#{1,6}\s*",
        "",
        text,
        flags=re.MULTILINE,
    )

    # Bold / italic
    text = re.sub(
        r"\*{1,2}([^*]+)\*{1,2}",
        r"\1",
        text,
    )

    # Inline code
    text = re.sub(
        r"`([^`]+)`",
        r"\1",
        text,
    )

    # Excessive blank lines
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()


# =============================================================================
# PIL IMAGE → BASE64
# =============================================================================

def _image_to_b64(
    pil_img,
) -> str:
    """
    Convert PIL image to JPEG base64 for Ollama.
    """

    from PIL import Image

    image = pil_img.copy()

    # Resize very large images.
    if max(image.size) > MAX_IMAGE_SIZE:

        image.thumbnail(
            (
                MAX_IMAGE_SIZE,
                MAX_IMAGE_SIZE,
            ),
            Image.LANCZOS,
        )

    buffer = io.BytesIO()

    image.convert(
        "RGB"
    ).save(
        buffer,
        format="JPEG",
        quality=JPEG_QUALITY,
        optimize=True,
    )

    return base64.b64encode(
        buffer.getvalue()
    ).decode(
        "utf-8"
    )


# =============================================================================
# SOURCE → PIL IMAGES
# =============================================================================

def _to_pil_images(
    source: Union[
        str,
        Path,
        np.ndarray,
    ],
) -> list:

    from PIL import Image

    # -------------------------------------------------------------------------
    # NumPy image
    # -------------------------------------------------------------------------

    if isinstance(
        source,
        np.ndarray,
    ):

        import cv2

        if source.ndim == 2:

            rgb = cv2.cvtColor(
                source,
                cv2.COLOR_GRAY2RGB,
            )

        else:

            rgb = cv2.cvtColor(
                source,
                cv2.COLOR_BGR2RGB,
            )

        return [
            Image.fromarray(
                rgb
            ).convert("RGB")
        ]

    # -------------------------------------------------------------------------
    # Path
    # -------------------------------------------------------------------------

    path = Path(
        source
    )

    if not path.exists():

        raise FileNotFoundError(
            f"Source not found: {path}"
        )

    # -------------------------------------------------------------------------
    # PDF
    # -------------------------------------------------------------------------

    if path.suffix.lower() == ".pdf":

        try:

            import fitz

        except ImportError as e:

            raise RuntimeError(
                "PyMuPDF is required for PDF OCR.\n"
                "Install it with:\n"
                "pip install PyMuPDF"
            ) from e

        doc = fitz.open(
            str(path)
        )

        images = []

        try:

            for page in doc:

                pix = page.get_pixmap(
                    dpi=PDF_DPI
                )

                image = Image.frombytes(
                    "RGB",
                    (
                        pix.width,
                        pix.height,
                    ),
                    pix.samples,
                )

                images.append(
                    image
                )

        finally:

            doc.close()

        return images

    # -------------------------------------------------------------------------
    # Normal image
    # -------------------------------------------------------------------------

    return [
        Image.open(
            path
        ).convert("RGB")
    ]


# =============================================================================
# NOTES
# =============================================================================

def _write_notes(
    path: Path,
    source: str,
    raw: str,
    summary: str,
):
    """
    Write notes for presentation.py.
    """

    path.write_text(
        f"=== AI Notes — {source} ===\n\n"
        f"[Summary — {OLLAMA_MODEL}]\n"
        f"{summary}\n\n"
        f"[Full Extracted Text]\n"
        f"{raw}\n",
        encoding="utf-8",
    )


# =============================================================================
# PROMPTS
# =============================================================================

EXTRACT_PROMPT = """
You are an OCR and document-understanding assistant.

Carefully inspect the provided image.

Extract ALL visible text from the image.

Include:
- headings
- paragraphs
- bullet points
- numbered lists
- labels
- tables
- diagrams containing readable text
- equations when readable
- handwritten text when readable

Preserve the logical reading order.

Do not describe the image.
Do not summarize.
Do not explain anything.

Output ONLY the extracted text.
"""


def _summary_prompt(
    raw_text: str,
) -> str:

    return f"""
You are an educational presentation summarization assistant.

Summarize the following OCR text.

Requirements:
- 3 to 5 clear sentences.
- Explain the main ideas.
- Keep important technical terminology.
- Do not invent information.
- Do not use Markdown.
- Do not use bullet points.
- Do not use hashtags.
- Do not use asterisks.
- Use plain readable paragraphs.

OCR text:

{raw_text[:8000]}
"""


# =============================================================================
# MAIN OCR API
# =============================================================================

def ocr_and_summarize(
    source: Union[
        str,
        Path,
        np.ndarray,
    ],
    slide_folder: Union[
        str,
        Path,
        None,
    ] = None,
    slide_num: int = 0,
    progress_cb: Optional[
        Callable[[str], None]
    ] = None,
    output_dir: Union[
        str,
        Path,
        None,
    ] = None,
    source_name: Optional[
        str
    ] = None,
    save: bool = True,
) -> OcrResult:
    """
    Image/PDF → Qwen2.5-VL → OCR + summary.

    Results:
        last_ocr_result.json

    Optional slide notes:
        slide_001_notes.txt
        slide_002_notes.txt
        ...
    """

    def progress(
        message: str,
    ):

        if progress_cb:

            try:
                progress_cb(
                    message
                )
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Ollama availability
    # -------------------------------------------------------------------------

    progress(
        "Checking Ollama…"
    )

    if not _ollama_available():

        return OcrResult(
            raw_text="",
            summary="",
            notes_path=None,
            model_used=OLLAMA_MODEL,
            source=str(source),
            error=(
                "Ollama is not running.\n\n"
                "Start Ollama before using AI OCR."
            ),
        )

    # -------------------------------------------------------------------------
    # Load images
    # -------------------------------------------------------------------------

    progress(
        "Loading image(s)…"
    )

    try:

        images = _to_pil_images(
            source
        )

    except Exception as e:

        return OcrResult(
            raw_text="",
            summary="",
            notes_path=None,
            model_used=OLLAMA_MODEL,
            source=str(source),
            error=str(e),
        )

    if not images:

        return OcrResult(
            raw_text="",
            summary="",
            notes_path=None,
            model_used=OLLAMA_MODEL,
            source=str(source),
            error="No images found.",
        )

    # -------------------------------------------------------------------------
    # Source name
    # -------------------------------------------------------------------------

    source_str = (
        str(source)
        if not isinstance(
            source,
            np.ndarray,
        )
        else
        f"canvas_{int(time.time())}"
    )

    name = (
        source_name
        or
        Path(
            source_str
        ).stem
    )

    # -------------------------------------------------------------------------
    # Limit pages
    # -------------------------------------------------------------------------

    selected_images = images[
        :MAX_PAGES_PER_REQUEST
    ]

    total_pages = len(
        images
    )

    if total_pages > MAX_PAGES_PER_REQUEST:

        progress(
            f"Using first "
            f"{MAX_PAGES_PER_REQUEST} "
            f"of {total_pages} pages…"
        )

    # -------------------------------------------------------------------------
    # Convert images to base64
    # -------------------------------------------------------------------------

    progress(
        f"Encoding {len(selected_images)} page(s)…"
    )

    encoded_images = [
        _image_to_b64(
            image
        )
        for image
        in selected_images
    ]

    # -------------------------------------------------------------------------
    # OCR
    # -------------------------------------------------------------------------

    extracted_parts = []

    for index, image_b64 in enumerate(
        encoded_images
    ):

        if len(
            encoded_images
        ) > 1:

            progress(
                f"Extracting page "
                f"{index + 1}/"
                f"{len(encoded_images)}…"
            )

        else:

            progress(
                "Extracting text with "
                "Qwen2.5-VL…"
            )

        text = _call_ollama(
            prompt=EXTRACT_PROMPT,
            images_b64=[
                image_b64
            ],
            max_tokens=1500,
        )

        extracted_parts.append(
            text
        )

    # -------------------------------------------------------------------------
    # Combine OCR
    # -------------------------------------------------------------------------

    if len(
        extracted_parts
    ) == 1:

        raw_text = (
            extracted_parts[0]
        )

    else:

        raw_text = "\n\n".join(
            f"[Page {i + 1}]\n{text}"
            for i, text
            in enumerate(
                extracted_parts
            )
        )

    # -------------------------------------------------------------------------
    # Detect Ollama errors
    # -------------------------------------------------------------------------

    if raw_text.startswith(
        "[Ollama error:"
    ):

        return OcrResult(
            raw_text="",
            summary="",
            notes_path=None,
            model_used=OLLAMA_MODEL,
            source=source_str,
            pages=total_pages,
            error=raw_text,
        )

    # -------------------------------------------------------------------------
    # Summarize
    # -------------------------------------------------------------------------

    progress(
        "Generating summary with Qwen2.5-VL…"
    )

    summary = _call_ollama(
        prompt=_summary_prompt(
            raw_text
        ),
        images_b64=None,
        max_tokens=500,
    )

    if summary.startswith(
        "[Ollama error:"
    ):

        return OcrResult(
            raw_text=raw_text,
            summary="",
            notes_path=None,
            model_used=OLLAMA_MODEL,
            source=source_str,
            pages=total_pages,
            error=summary,
        )

    # -------------------------------------------------------------------------
    # Save JSON
    # -------------------------------------------------------------------------

    result_dict = {
        "raw_text": raw_text,
        "summary": summary,
        "model_used": OLLAMA_MODEL,
        "source": source_str,
        "pages": total_pages,
        "timestamp": time.time(),
    }

    try:

        _LAST_OCR_FILE.write_text(
            json.dumps(
                result_dict,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        progress(
            "Saved last_ocr_result.json"
        )

    except Exception as e:

        progress(
            f"Could not save OCR JSON: {e}"
        )

    # -------------------------------------------------------------------------
    # Save notes
    # -------------------------------------------------------------------------

    notes_path = None

    if (
        save
        and
        summary.strip()
    ):

        if slide_folder:

            output_path = Path(
                slide_folder
            )

            filename = (
                f"slide_"
                f"{slide_num + 1:03d}"
                f"_notes.txt"
            )

        elif output_dir:

            output_path = Path(
                output_dir
            )

            filename = (
                f"{name}_notes.txt"
            )

        else:

            if isinstance(
                source,
                np.ndarray,
            ):

                output_path = (
                    _DOCS_DIR
                )

            else:

                output_path = (
                    Path(
                        source_str
                    ).parent
                )

            filename = (
                f"{name}_notes.txt"
            )

        try:

            output_path.mkdir(
                parents=True,
                exist_ok=True,
            )

            notes_path = (
                output_path
                / filename
            )

            _write_notes(
                notes_path,
                name,
                raw_text,
                summary,
            )

            progress(
                f"Notes saved → "
                f"{filename}"
            )

        except Exception as e:

            progress(
                f"Could not save notes: {e}"
            )

    return OcrResult(
        raw_text=raw_text,
        summary=summary,
        notes_path=notes_path,
        model_used=OLLAMA_MODEL,
        source=source_str,
        pages=total_pages,
    )


# =============================================================================
# ALL SLIDES
# =============================================================================

def ocr_all_slides(
    slide_paths: list,
    slide_folder: Union[
        str,
        Path,
    ],
    progress_cb=None,
) -> OcrResult:
    """
    OCR every slide and generate one combined summary.
    """

    def progress(
        message,
    ):

        if progress_cb:

            try:
                progress_cb(
                    message
                )
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Ollama
    # -------------------------------------------------------------------------

    if not _ollama_available():

        return OcrResult(
            raw_text="",
            summary="",
            notes_path=None,
            model_used=OLLAMA_MODEL,
            source="all_slides",
            error=(
                "Ollama is not running."
            ),
        )

    if not slide_paths:

        return OcrResult(
            raw_text="",
            summary="",
            notes_path=None,
            model_used=OLLAMA_MODEL,
            source="all_slides",
            pages=0,
            error="No slides supplied.",
        )

    total = len(
        slide_paths
    )

    all_text_parts = []

    # -------------------------------------------------------------------------
    # Read each slide
    # -------------------------------------------------------------------------

    for i, slide_path in enumerate(
        slide_paths
    ):

        progress(
            f"Reading slide "
            f"{i + 1}/{total}…"
        )

        try:

            images = _to_pil_images(
                slide_path
            )

            if not images:

                all_text_parts.append(
                    f"[Slide {i + 1}]\n"
                    "(No image found.)"
                )

                continue

            image_b64 = (
                _image_to_b64(
                    images[0]
                )
            )

            text = _call_ollama(
                prompt=EXTRACT_PROMPT,
                images_b64=[
                    image_b64
                ],
                max_tokens=1200,
            )

            all_text_parts.append(
                f"[Slide {i + 1}]\n"
                f"{text}"
            )

        except Exception as e:

            all_text_parts.append(
                f"[Slide {i + 1}]\n"
                f"(Error: {e})"
            )

    raw_text = "\n\n".join(
        all_text_parts
    )

    # -------------------------------------------------------------------------
    # Combined summary
    # -------------------------------------------------------------------------

    progress(
        "Generating combined presentation summary…"
    )

    summary_prompt = f"""
You are summarizing an entire presentation.

Review the extracted content below.

Write a clear summary that:
- explains what the presentation is about,
- covers the important points,
- explains important technical concepts,
- connects related ideas,
- gives a concluding thought.

Requirements:
- Under 300 words.
- Plain text only.
- No Markdown.
- No bullet points.
- No hashtags.
- No asterisks.
- Do not invent facts.

Presentation content:

{raw_text[:12000]}
"""

    summary = _call_ollama(
        prompt=summary_prompt,
        images_b64=None,
        max_tokens=700,
    )

    if summary.startswith(
        "[Ollama error:"
    ):

        return OcrResult(
            raw_text=raw_text,
            summary="",
            notes_path=None,
            model_used=OLLAMA_MODEL,
            source="all_slides",
            pages=total,
            error=summary,
        )

    # -------------------------------------------------------------------------
    # Save combined notes
    # -------------------------------------------------------------------------

    output_path = Path(
        slide_folder
    )

    output_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    notes_path = (
        output_path
        / "all_slides_summary.txt"
    )

    try:

        _write_notes(
            notes_path,
            "all_slides",
            raw_text,
            summary,
        )

    except Exception:

        notes_path = None

    # -------------------------------------------------------------------------
    # Update JSON
    # -------------------------------------------------------------------------

    try:

        _LAST_OCR_FILE.write_text(
            json.dumps(
                {
                    "raw_text": raw_text,
                    "summary": summary,
                    "model_used": OLLAMA_MODEL,
                    "source": "all_slides",
                    "pages": total,
                    "timestamp": time.time(),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    except Exception:

        pass

    return OcrResult(
        raw_text=raw_text,
        summary=summary,
        notes_path=notes_path,
        model_used=OLLAMA_MODEL,
        source="all_slides",
        pages=total,
    )


# =============================================================================
# FILE HELPERS
# =============================================================================

def read_last_output() -> Optional[dict]:
    """
    Read last_output.json created by Canvas/Sketch.
    """

    if not _LAST_OUT_FILE.exists():
        return None

    try:

        data = json.loads(
            _LAST_OUT_FILE.read_text(
                encoding="utf-8"
            )
        )

        if (
            "path" in data
            and
            Path(
                data["path"]
            ).exists()
        ):

            return data

    except Exception:

        pass

    return None


def read_last_ocr_result() -> Optional[dict]:
    """
    Read the most recent OCR result.
    """

    if not _LAST_OCR_FILE.exists():
        return None

    try:

        return json.loads(
            _LAST_OCR_FILE.read_text(
                encoding="utf-8"
            )
        )

    except Exception:

        return None


def ocr_last_output(
    **kwargs
) -> Optional[OcrResult]:
    """
    Run OCR on the last saved Canvas/Sketch image.
    """

    info = read_last_output()

    if info is None:
        return None

    return ocr_and_summarize(
        info["path"],
        **kwargs,
    )


def load_slide_notes(
    slide_folder: Union[
        str,
        Path,
    ],
    slide_num: int,
) -> str:
    """
    Load notes for a specific presentation slide.
    """

    path = (
        Path(slide_folder)
        /
        f"slide_{slide_num + 1:03d}_notes.txt"
    )

    if not path.exists():
        return ""

    try:

        return path.read_text(
            encoding="utf-8"
        )

    except Exception:

        return ""


# =============================================================================
# SIMPLE STANDALONE TEST
# =============================================================================

def test_ollama() -> bool:
    """
    Simple diagnostic helper.

    Returns True when Ollama answers successfully.
    """

    if not _ollama_available():

        print(
            "❌ Ollama is not running."
        )

        return False

    print(
        f"✅ Ollama reachable: "
        f"{OLLAMA_URL}"
    )

    print(
        f"Model: {OLLAMA_MODEL}"
    )

    result = _call_ollama(
        prompt=(
            "Reply with exactly: "
            "OLLAMA_OK"
        ),
        images_b64=None,
        max_tokens=20,
    )

    print(
        "Response:",
        result,
    )

    return not result.startswith(
        "[Ollama error:"
    )


# =============================================================================
# STANDALONE
# =============================================================================

if __name__ == "__main__":

    print(
        "=========================================="
    )

    print(
        " PDF Studio - Ollama OCR Pipeline"
    )

    print(
        "=========================================="
    )

    print(
        f"Ollama URL : {OLLAMA_URL}"
    )

    print(
        f"Model      : {OLLAMA_MODEL}"
    )

    print()

    if test_ollama():

        print()
        print(
            "Ollama is ready."
        )

        print(
            f"Make sure the model exists with:"
        )

        print(
            f"  ollama run {OLLAMA_MODEL}"
        )

    else:

        print()
        print(
            "Ollama is not ready."
        )