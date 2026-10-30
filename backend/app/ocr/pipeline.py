"""
OCR pipeline: extracts text from scanned documents/images, entirely offline.
Tesseract is the default (lightweight, no model download at runtime beyond
the language packs baked into the image); PaddleOCR is used as a fallback
for harder layouts (tables, multi-column, handwriting-adjacent print) since
it generally performs better on structured documents. Both run fully local.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

import pytesseract
from PIL import Image


@dataclass
class OCRLine:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x, y, w, h


@dataclass
class OCRResult:
    full_text: str
    lines: list[OCRLine]
    engine_used: str
    mean_confidence: float


def _tesseract_extract(image_path: str) -> OCRResult:
    img = Image.open(image_path)
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    lines: list[OCRLine] = []
    confidences: list[float] = []
    for i, text in enumerate(data["text"]):
        if not text.strip():
            continue
        conf = float(data["conf"][i]) if data["conf"][i] != "-1" else 0.0
        confidences.append(conf)
        lines.append(OCRLine(
            text=text,
            confidence=conf,
            bbox=(data["left"][i], data["top"][i], data["width"][i], data["height"][i]),
        ))

    full_text = " ".join(l.text for l in lines)
    mean_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return OCRResult(full_text=full_text, lines=lines, engine_used="tesseract", mean_confidence=mean_conf)


def _paddleocr_extract(image_path: str) -> OCRResult:
    # Imported lazily: PaddleOCR pulls in paddlepaddle, a heavy dependency
    # only needed when the Tesseract confidence is too low.
    from paddleocr import PaddleOCR  # type: ignore

    ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    result = ocr.ocr(image_path, cls=True)

    lines: list[OCRLine] = []
    confidences: list[float] = []
    for block in (result or []):
        for bbox_pts, (text, conf) in block:
            xs = [p[0] for p in bbox_pts]
            ys = [p[1] for p in bbox_pts]
            lines.append(OCRLine(
                text=text, confidence=conf * 100,
                bbox=(int(min(xs)), int(min(ys)), int(max(xs) - min(xs)), int(max(ys) - min(ys))),
            ))
            confidences.append(conf * 100)

    full_text = " ".join(l.text for l in lines)
    mean_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return OCRResult(full_text=full_text, lines=lines, engine_used="paddleocr", mean_confidence=mean_conf)


def extract(image_path: str, confidence_fallback_threshold: float = 60.0) -> OCRResult:
    """
    Extract text with Tesseract first (fast); if mean confidence is below
    threshold, retry with PaddleOCR (better on tables/complex layouts,
    slower / heavier). Both engines run fully offline.
    """
    if not Path(image_path).exists():
        return OCRResult(full_text="", lines=[], engine_used="none", mean_confidence=0.0)

    result = _tesseract_extract(image_path)
    if result.mean_confidence < confidence_fallback_threshold:
        try:
            paddle_result = _paddleocr_extract(image_path)
            if paddle_result.mean_confidence > result.mean_confidence:
                return paddle_result
        except ImportError:
            pass  # PaddleOCR not installed in this deployment — keep Tesseract result
    return result
