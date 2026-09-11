import os
from enum import Enum


class OCRLanguage(str, Enum):
    english = "english"
    hindi = "hindi"
    bengali = "bengali"


# EasyOCR restricts which languages can be combined in one Reader.
# Devanagari-script languages (Hindi, Marathi, Nepali) form one compatible group.
# Bengali is only compatible with English and Assamese.
LANGUAGE_GROUPS = {
    OCRLanguage.english: ["en"],
    OCRLanguage.hindi: ["en", "hi"],
    OCRLanguage.bengali: ["en", "bn"],
}

# Cache loaded readers so we don't reload the same language model on every request
_reader_cache = {}


def get_reader(language: OCRLanguage):
    from easyocr import Reader

    if language not in _reader_cache:
        print(f"[OCR] Loading model for '{language.value}' (first time only)...")
        _reader_cache[language] = Reader(LANGUAGE_GROUPS[language], gpu=False)
    return _reader_cache[language]


def extract_text_from_pdf(pdf_path: str, language: OCRLanguage = OCRLanguage.english) -> str:
    """
    Converts every page of a PDF to an image,
    runs EasyOCR (using the selected language model) on each page,
    and returns all extracted text.
    """

    from pdf2image import convert_from_path
    import numpy as np

    print(f"[OCR] Starting PDF processing (language: {language.value})...")

    reader = get_reader(language)

    pages = convert_from_path(pdf_path)

    total_pages = len(pages)

    print(f"[OCR] Total pages: {total_pages}")

    extracted_lines = []

    for i, page in enumerate(pages):

        page_number = i + 1

        print(f"[OCR] Processing page {page_number}/{total_pages}...")

        image_array = np.array(page)

        results = reader.readtext(image_array)

        for (_, text, _) in results:
            extracted_lines.append(text)

        print(f"[OCR] Finished page {page_number}/{total_pages}")

    print("[OCR] Processing complete.")

    return "\n".join(extracted_lines)