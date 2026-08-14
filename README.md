# PDF Slide & Draw Studio

PDF Slide & Draw Studio is a modular desktop application built with Python
and PyQt6 for PDF presentation management, digital drawing, hand-tracked
sketching, and AI-powered OCR and summarization.

## Features

- PDF upload and conversion to PNG slides
- Advanced drawing canvas
- ER/UML/Flowchart drawing
- Text, shapes, undo, and save
- Webcam-based hand tracking
- OpenCV and MediaPipe marker detection
- Built-in presentation mode
- Document and output management
- AI-powered OCR
- AI-powered summarization
- Ollama + Qwen2.5-VL integration
- Streamlit-based summarization interface

## Technologies

- Python
- PyQt6
- OpenCV
- MediaPipe
- NumPy
- PyMuPDF
- Pillow
- Streamlit
- Ollama
- Qwen2.5-VL

## Project Structure

```text
main.py
main_window.py
config.py
utils.py
workers.py

home.py
canvas.py
sketch.py
documents.py
summarizer.py
summarize.py
ocr_pipeline.py