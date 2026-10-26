"""Распознавание текста на сканах и фотографиях документов (Tesseract)."""

from pathlib import Path

import pypdfium2
import pytesseract
from PIL import Image

from . import config

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
RENDER_DPI = 200


class OcrUnavailable(Exception):
    """Tesseract не установлен на сервере."""


def _languages() -> str:
    """Языки из настроек, которые реально установлены; без них Tesseract использует любой доступный."""
    try:
        installed = set(pytesseract.get_languages())
    except pytesseract.TesseractNotFoundError as error:
        raise OcrUnavailable("Tesseract не установлен") from error
    wanted = [lang for lang in config.OCR_LANGUAGES.split("+") if lang in installed]
    return "+".join(wanted) or "eng"


def is_available() -> bool:
    try:
        _languages()
        return True
    except OcrUnavailable:
        return False


def image_to_text(image: Image.Image) -> str:
    return pytesseract.image_to_string(image, lang=_languages())


def pdf_to_text(path: Path) -> str:
    """Распознаёт первые страницы PDF без текстового слоя."""
    document = pypdfium2.PdfDocument(str(path))
    pages = min(len(document), config.OCR_MAX_PAGES)
    scale = RENDER_DPI / 72
    return "\n".join(image_to_text(document[i].render(scale=scale).to_pil()) for i in range(pages))


def file_to_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return pdf_to_text(path)
    with Image.open(path) as image:
        return image_to_text(image)
