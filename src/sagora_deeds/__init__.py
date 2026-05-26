"""Sagora deeds package.

The package does not import pipeline modules here on purpose. Keeping package
import side effects empty lets the lightweight API Docker image start without
installing OCR/Gemini-only dependencies.
"""

__all__: list[str] = []
