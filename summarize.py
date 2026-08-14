# summarize.py
"""
PDF Studio - Multimodal Summarizer

Backend:
    Ollama + Qwen2.5-VL

Can summarize:
    - pasted text
    - PDF files
    - images
    - web article URLs
    - last OCR result from Canvas / Sketch

This file is launched by summarizer.py through Streamlit.
"""

from __future__ import annotations

import base64
import io
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image


# =============================================================================
# CONFIG
# =============================================================================

ROOT_DIR = Path(__file__).resolve().parent

OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://localhost:11434/api/chat",
).strip()

DEFAULT_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5vl:3b",
).strip()

OLLAMA_TIMEOUT = 120

STREAMLIT_PORT = int(
    os.getenv(
        "STREAMLIT_PORT",
        "8501",
    )
)


# =============================================================================
# OPTIONAL SELF-BOOT
# =============================================================================

def _find_free_port() -> int:
    """
    Find an available local TCP port.
    """

    with socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    ) as sock:

        sock.bind(
            ("", 0)
        )

        return sock.getsockname()[1]


def _streamlit_running(port: int) -> bool:
    """
    Check whether Streamlit is already reachable.
    """

    try:

        with socket.create_connection(
            (
                "localhost",
                port,
            ),
            timeout=0.5,
        ):
            return True

    except OSError:

        return False


def _boot():
    """
    Optional direct execution:

        python summarize.py

    It starts Streamlit and opens the page.
    """

    port = STREAMLIT_PORT

    if _streamlit_running(port):
        selected_port = port

    else:

        selected_port = port

        # If configured port is occupied by something else,
        # use another free port.
        try:

            with socket.socket(
                socket.AF_INET,
                socket.SOCK_STREAM,
            ) as sock:

                sock.bind(
                    ("", selected_port)
                )

        except OSError:

            selected_port = _find_free_port()

    env = {
        **os.environ,
        "_SUMMARIZE_WORKER": "1",
        "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
    }

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            os.path.abspath(__file__),
            "--server.port",
            str(selected_port),
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ],
        env=env,
    )

    started = False

    for _ in range(30):

        time.sleep(0.5)

        if _streamlit_running(
            selected_port
        ):

            started = True
            break

    if not started:

        proc.terminate()

        print(
            f"[summarize] Streamlit did not start "
            f"on port {selected_port}"
        )

        sys.exit(1)

    url = (
        f"http://localhost:{selected_port}"
    )

    try:

        import webview

        webview.create_window(
            "Summarize App",
            url,
            width=1100,
            height=800,
        )

        webview.start()

    except ImportError:

        import webbrowser

        webbrowser.open(
            url
        )

        try:
            proc.wait()
        except KeyboardInterrupt:
            pass

    finally:

        if proc.poll() is None:

            proc.terminate()

            try:
                proc.wait(
                    timeout=3
                )
            except Exception:
                proc.kill()

    sys.exit(0)


# =============================================================================
# DETECT STREAMLIT WORKER
# =============================================================================

_inside_streamlit = (
    os.environ.get(
        "_SUMMARIZE_WORKER"
    ) == "1"
    or
    "streamlit" in sys.modules
    or
    any(
        "streamlit" in str(arg).lower()
        for arg in sys.argv
    )
)


if not _inside_streamlit:
    _boot()


# =============================================================================
# STREAMLIT IMPORTS
# =============================================================================

import streamlit as st

from ocr_pipeline import (
    read_last_ocr_result,
)


# =============================================================================
# OLLAMA
# =============================================================================

def ollama_available() -> bool:
    """
    Check whether Ollama is running.
    """

    try:

        with socket.create_connection(
            ("localhost", 11434),
            timeout=1,
        ):
            return True

    except OSError:

        return False


def call_ollama(
    prompt: str,
    images_b64: list[str] | None = None,
    max_tokens: int = 300,
) -> str:
    """
    Call Ollama's /api/chat endpoint.

    Qwen2.5-VL receives optional images through
    the user message's `images` field.
    """

    payload = {
        "model": DEFAULT_MODEL,

        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],

        "stream": False,

        "options": {
            "num_predict": int(
                max_tokens
            ),
            "temperature": 0.2,
        },
    }

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

        message = data.get(
            "message",
            {},
        )

        text = message.get(
            "content",
            "",
        )

        if not text:

            # Compatibility fallback
            text = data.get(
                "response",
                "",
            )

        return text.strip()

    except requests.exceptions.ConnectionError:

        return (
            "Error connecting to Ollama: "
            "Ollama is not running."
        )

    except requests.exceptions.Timeout:

        return (
            "Error connecting to Ollama: "
            "request timed out."
        )

    except Exception as e:

        return (
            f"Error connecting to Ollama: {e}"
        )


# =============================================================================
# IMAGE → BASE64
# =============================================================================

def image_to_base64(
    image: Image.Image,
) -> str:
    """
    Convert PIL image into JPEG base64.
    """

    image = image.copy()

    if max(
        image.size
    ) > 1280:

        image.thumbnail(
            (
                1280,
                1280,
            ),
            Image.LANCZOS,
        )

    buffer = io.BytesIO()

    image.convert(
        "RGB"
    ).save(
        buffer,
        format="JPEG",
        quality=85,
    )

    return base64.b64encode(
        buffer.getvalue()
    ).decode(
        "utf-8"
    )


# =============================================================================
# PDF → IMAGES
# =============================================================================

def pdf_to_images(
    pdf_bytes: bytes,
) -> list[Image.Image]:
    """
    Render PDF pages using PyMuPDF.
    """

    try:

        import fitz

        doc = fitz.open(
            stream=pdf_bytes,
            filetype="pdf",
        )

        images = []

        try:

            for page in doc:

                pix = page.get_pixmap(
                    dpi=150
                )

                img = Image.frombytes(
                    "RGB",
                    [
                        pix.width,
                        pix.height,
                    ],
                    pix.samples,
                )

                images.append(
                    img
                )

        finally:

            doc.close()

        return images

    except Exception as e:

        st.error(
            "Failed to render PDF using "
            f"PyMuPDF: {e}"
        )

        return []


# =============================================================================
# WEB ARTICLE
# =============================================================================

def fetch_article_text(
    url: str,
) -> str:

    try:

        from bs4 import BeautifulSoup

    except ImportError:

        raise RuntimeError(
            "BeautifulSoup is not installed.\n"
            "Run: pip install beautifulsoup4"
        )

    response = requests.get(
        url,
        timeout=15,
        headers={
            "User-Agent":
                "Mozilla/5.0 "
                "PDF-Studio-Summarizer/1.0"
        },
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    # Remove things unlikely to be useful.
    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "nav",
            "footer",
            "header",
        ]
    ):

        tag.decompose()

    paragraphs = []

    for paragraph in soup.find_all(
        "p"
    ):

        text = paragraph.get_text(
            " ",
            strip=True,
        )

        if text:

            paragraphs.append(
                text
            )

    text = "\n\n".join(
        paragraphs
    )

    return text


# =============================================================================
# STREAMLIT UI
# =============================================================================

def main():

    st.set_page_config(
        page_title="Summarize App",
        page_icon="📚",
        layout="wide",
    )

    # -------------------------------------------------------------------------
    # Header
    # -------------------------------------------------------------------------

    st.title(
        "📚 Multimodal Summarizer"
    )

    st.caption(
        f"Ollama + {DEFAULT_MODEL}"
    )

    # -------------------------------------------------------------------------
    # Ollama status
    # -------------------------------------------------------------------------

    if ollama_available():

        st.success(
            f"✅ Ollama connected  •  "
            f"Model: {DEFAULT_MODEL}"
        )

    else:

        st.error(
            "❌ Ollama is not running."
        )

        st.code(
            "ollama serve"
        )

    # -------------------------------------------------------------------------
    # Sidebar
    # -------------------------------------------------------------------------

    with st.sidebar:

        st.header(
            "Summarize"
        )

        modes = [
            "Text",
            "PDF upload",
            "Image",
            "URL",
            "Canvas / Last OCR",
        ]

        input_mode = st.radio(
            "Select Mode",
            modes,
        )

        st.divider()

        max_tokens = st.number_input(
            "Max Output Tokens",
            min_value=50,
            max_value=1000,
            value=250,
            step=50,
        )

        st.divider()

        st.write(
            "**Model**"
        )

        st.code(
            DEFAULT_MODEL
        )

        run_btn = st.button(
            "▶ Generate Summary",
            type="primary",
            use_container_width=True,
        )

    # -------------------------------------------------------------------------
    # Working variables
    # -------------------------------------------------------------------------

    prompt = (
        f"Summarize the content in "
        f"under {max_tokens} words."
    )

    images_b64 = []

    text_content = ""

    source_description = ""

    # -------------------------------------------------------------------------
    # TEXT
    # -------------------------------------------------------------------------

    if input_mode == "Text":

        text_content = st.text_area(
            "Paste text here",
            height=250,
            placeholder=(
                "Paste your text, lecture notes, "
                "article, or other material here..."
            ),
        )

        if text_content.strip():

            prompt = (
                "Summarize the following text "
                "clearly and accurately.\n\n"
                f"{text_content}"
            )

            source_description = (
                "Pasted text"
            )

    # -------------------------------------------------------------------------
    # PDF
    # -------------------------------------------------------------------------

    elif input_mode == "PDF upload":

        uploaded = st.file_uploader(
            "Upload PDF",
            type=["pdf"],
        )

        if uploaded:

            pdf_bytes = uploaded.read()

            images = pdf_to_images(
                pdf_bytes
            )

            if images:

                total = len(
                    images
                )

                used = min(
                    total,
                    4
                )

                st.success(
                    f"Rendered {total} page(s)."
                )

                if total > 4:

                    st.warning(
                        f"Only the first 4 of "
                        f"{total} pages will be "
                        f"processed."
                    )

                # Show first pages.
                preview_cols = st.columns(
                    min(4, used)
                )

                for i in range(
                    used
                ):

                    with preview_cols[i]:

                        st.image(
                            images[i],
                            caption=(
                                f"Page {i + 1}"
                            ),
                            width=200,
                        )

                images_b64 = [
                    image_to_base64(
                        image
                    )
                    for image
                    in images[:4]
                ]

                prompt = """
Analyze the provided presentation/document pages.

Summarize the important content from the document.

Include:
- the main topic,
- important concepts,
- important technical details,
- key conclusions.

Do not invent information.
Write a clear educational summary.
"""

                source_description = (
                    f"PDF: {uploaded.name}"
                )

    # -------------------------------------------------------------------------
    # IMAGE
    # -------------------------------------------------------------------------

    elif input_mode == "Image":

        uploaded = st.file_uploader(
            "Upload Image",
            type=[
                "png",
                "jpg",
                "jpeg",
                "bmp",
                "webp",
            ],
        )

        if uploaded:

            image = Image.open(
                uploaded
            ).convert("RGB")

            st.image(
                image,
                width=400,
                caption=uploaded.name,
            )

            images_b64 = [
                image_to_base64(
                    image
                )
            ]

            prompt = """
Analyze this image carefully.

Extract and understand the visible content,
then provide a clear summary of the important
information.

Do not invent information.
"""

            source_description = (
                f"Image: {uploaded.name}"
            )

    # -------------------------------------------------------------------------
    # URL
    # -------------------------------------------------------------------------

    elif input_mode == "URL":

        url = st.text_input(
            "Enter Web Article URL"
        )

        if url.strip():

            try:

                text_content = (
                    fetch_article_text(
                        url.strip()
                    )
                )

                if len(
                    text_content
                ) > 12000:

                    text_content = (
                        text_content[:12000]
                    )

                    st.warning(
                        "Article was truncated "
                        "to 12,000 characters."
                    )

                if text_content:

                    st.success(
                        "Article text loaded."
                    )

                    with st.expander(
                        "Preview article text"
                    ):

                        st.text(
                            text_content[:5000]
                        )

                    prompt = (
                        "Summarize this web article "
                        "clearly and accurately.\n\n"
                        f"{text_content}"
                    )

                    source_description = (
                        f"URL: {url}"
                    )

                else:

                    st.warning(
                        "Could not extract article text."
                    )

            except Exception as e:

                st.error(
                    f"Failed to fetch article: {e}"
                )

    # -------------------------------------------------------------------------
    # CANVAS / LAST OCR
    # -------------------------------------------------------------------------

    elif input_mode == (
        "Canvas / Last OCR"
    ):

        ocr_data = (
            read_last_ocr_result()
        )

        if ocr_data:

            st.info(
                "Loaded from source: "
                f"{ocr_data.get('source', 'Unknown')}"
            )

            text_content = (
                ocr_data.get(
                    "raw_text",
                    "",
                )
            )

            if text_content:

                st.text_area(
                    "Extracted OCR Text",
                    value=text_content,
                    height=250,
                    disabled=True,
                )

                prompt = (
                    "Summarize this OCR text "
                    "clearly and accurately.\n\n"
                    f"{text_content}"
                )

                source_description = (
                    "Last OCR result"
                )

            else:

                st.warning(
                    "The OCR result contains no text."
                )

        else:

            st.warning(
                "No recent OCR result found in "
                "last_ocr_result.json."
            )

            st.caption(
                "Save and run AI OCR from Canvas "
                "or Sketch first."
            )

    # -------------------------------------------------------------------------
    # GENERATE
    # -------------------------------------------------------------------------

    if run_btn:

        if not ollama_available():

            st.error(
                "Ollama is not running."
            )

            st.code(
                "ollama serve"
            )

            st.stop()

        if (
            not text_content.strip()
            and
            not images_b64
        ):

            st.warning(
                "Please provide input data before "
                "running the summarizer."
            )

            st.stop()

        with st.spinner(
            f"Processing with "
            f"{DEFAULT_MODEL}..."
        ):

            result = call_ollama(
                prompt,
                images_b64=(
                    images_b64
                    if images_b64
                    else None
                ),
                max_tokens=int(
                    max_tokens
                ),
            )

        if not result:

            st.error(
                "The model returned an empty response."
            )

            st.stop()

        if result.startswith(
            "Error connecting to Ollama:"
        ):

            st.error(
                result
            )

            st.stop()

        # ---------------------------------------------------------------------
        # Result
        # ---------------------------------------------------------------------

        st.subheader(
            "📄 Summary Output"
        )

        st.markdown(
            result
        )

        # ---------------------------------------------------------------------
        # Save TXT
        # ---------------------------------------------------------------------

        saved_dir = (
            ROOT_DIR
            / "saved_outputs"
        )

        saved_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        timestamp = (
            datetime.now()
            .strftime(
                "%Y%m%d_%H%M%S"
            )
        )

        txt_path = (
            saved_dir
            /
            f"summary_{timestamp}.txt"
        )

        txt_path.write_text(
            result,
            encoding="utf-8",
        )

        st.download_button(
            label="⬇ Download Summary as TXT",
            data=result,
            file_name=(
                f"summary_{timestamp}.txt"
            ),
            mime="text/plain",
        )

        # ---------------------------------------------------------------------
        # Save PDF
        # ---------------------------------------------------------------------

        try:

            from fpdf import FPDF
            from fpdf.enums import (
                XPos,
                YPos,
            )

            pdf = FPDF()

            pdf.set_auto_page_break(
                auto=True,
                margin=15,
            )

            pdf.set_margins(
                15,
                15,
                15,
            )

            pdf.add_page()

            pdf.set_font(
                "Helvetica",
                style="B",
                size=14,
            )

            pdf.cell(
                0,
                10,
                "Summary Report",
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )

            pdf.set_font(
                "Helvetica",
                size=9,
            )

            pdf.cell(
                0,
                6,
                (
                    "Generated: "
                    +
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                ),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )

            pdf.cell(
                0,
                6,
                (
                    "Model: "
                    + DEFAULT_MODEL
                ),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )

            if source_description:

                pdf.cell(
                    0,
                    6,
                    (
                        "Source: "
                        + source_description
                    )[:110],
                    new_x=XPos.LMARGIN,
                    new_y=YPos.NEXT,
                )

            pdf.ln(4)

            pdf.set_font(
                "Helvetica",
                size=11,
            )

            for line in (
                result.split("\n")
            ):

                line = line.strip()

                if not line:

                    pdf.ln(4)

                    continue

                if line.startswith(
                    "## "
                ):

                    pdf.set_font(
                        "Helvetica",
                        style="B",
                        size=13,
                    )

                    pdf.multi_cell(
                        0,
                        8,
                        line[3:],
                        new_x=XPos.LMARGIN,
                        new_y=YPos.NEXT,
                    )

                    pdf.set_font(
                        "Helvetica",
                        size=11,
                    )

                elif line.startswith(
                    "# "
                ):

                    pdf.set_font(
                        "Helvetica",
                        style="B",
                        size=15,
                    )

                    pdf.multi_cell(
                        0,
                        9,
                        line[2:],
                        new_x=XPos.LMARGIN,
                        new_y=YPos.NEXT,
                    )

                    pdf.set_font(
                        "Helvetica",
                        size=11,
                    )

                elif (
                    line.startswith("**")
                    and
                    line.endswith("**")
                ):

                    pdf.set_font(
                        "Helvetica",
                        style="B",
                        size=11,
                    )

                    pdf.multi_cell(
                        0,
                        7,
                        line[2:-2],
                        new_x=XPos.LMARGIN,
                        new_y=YPos.NEXT,
                    )

                    pdf.set_font(
                        "Helvetica",
                        size=11,
                    )

                elif (
                    line.startswith("- ")
                    or
                    line.startswith("* ")
                ):

                    pdf.multi_cell(
                        0,
                        7,
                        f"  •  {line[2:]}",
                        new_x=XPos.LMARGIN,
                        new_y=YPos.NEXT,
                    )

                else:

                    pdf.multi_cell(
                        0,
                        7,
                        line,
                        new_x=XPos.LMARGIN,
                        new_y=YPos.NEXT,
                    )

            pdf_path = (
                saved_dir
                /
                f"summary_{timestamp}.pdf"
            )

            pdf.output(
                str(pdf_path)
            )

            with open(
                pdf_path,
                "rb",
            ) as pdf_file:

                st.download_button(
                    label=(
                        "⬇ Download Summary as PDF"
                    ),
                    data=pdf_file.read(),
                    file_name=(
                        f"summary_{timestamp}.pdf"
                    ),
                    mime="application/pdf",
                )

        except ImportError:

            st.info(
                "💡 Install fpdf2 for PDF export:\n"
                "pip install fpdf2"
            )

        except Exception as pdf_err:

            st.warning(
                f"PDF export failed: {pdf_err}"
            )

        # ---------------------------------------------------------------------
        # Save message
        # ---------------------------------------------------------------------

        st.success(
            "✅ Summary auto-saved to: "
            f"saved_outputs/"
            f"summary_{timestamp}.txt"
        )


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    main()