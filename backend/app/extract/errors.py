from __future__ import annotations


class ExtractError(Exception):
    """Base error for PDF text extraction / parsing."""


class PdfReadError(ExtractError):
    pass


class ParseError(ExtractError):
    pass
