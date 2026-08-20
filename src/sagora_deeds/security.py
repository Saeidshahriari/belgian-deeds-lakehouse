"""Pre-processing security checks for untrusted PDF input.

Deed PDFs come from an external, public source (the Belgian Gazette dataset).
Two risks matter before that content is trusted by the rest of the pipeline:

1. Malicious PDF structure. A PDF can carry JavaScript, auto-run actions, launch
   actions, or embedded files. These target a PDF reader rather than this
   pipeline, but flagging them keeps active/executable content out of the corpus
   and out of anything a human later opens.

2. Prompt injection. The OCR/extracted text is handed to an LLM (Gemini). Text
   placed inside a document can try to hijack that model with instructions such
   as "ignore all previous instructions". Because the model sees the document
   text as input, an instruction hidden in a data field is a real attack vector.

Design stance: detect and report, never crash. The scanner does not delete files
and does not raise on a crafted PDF. It returns findings plus a severity, and the
caller decides what to do (process, flag, or skip). A single malicious PDF must
never be able to halt the whole batch, because that would turn one crafted file
into a denial-of-service against the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

import pikepdf


# PDF dictionary keys that indicate active or executable content. These are the
# names attackers use to make a PDF "do something" when opened, rather than just
# display text.
RISKY_PDF_KEYS: dict[str, str] = {
    "/JavaScript": "high",   # embedded JavaScript
    "/JS": "high",           # JavaScript action body
    "/Launch": "high",       # launches an external program
    "/EmbeddedFile": "high",  # a file hidden inside the PDF
    "/EmbeddedFiles": "high",
    "/RichMedia": "high",    # Flash/embedded media
    "/XFA": "medium",        # XML forms, historically abused
    "/OpenAction": "medium",  # runs automatically when the PDF opens
    "/AA": "medium",         # additional actions (on page open, etc.)
}

# Phrases that legitimate deed text never contains but prompt-injection payloads
# very often do. Kept deliberately small and specific to avoid false positives on
# ordinary French/Dutch legal language.
PROMPT_INJECTION_PATTERNS: list[str] = [
    r"ignore (all |the |your )?previous instructions",
    r"disregard (the |all )?(above|previous)",
    r"forget (everything|all previous|the above)",
    r"you are now",
    r"new instructions?:",
    r"system prompt",
    r"reveal (your|the) (prompt|instructions|system)",
    r"override (the |your )?(rules|schema|instructions)",
    r"do not follow the (schema|rules|instructions)",
    r"return all (data|records|rows)",
]


@dataclass(slots=True)
class SecurityFinding:
    """One thing the scanner flagged, with enough context to explain it."""

    category: str      # "pdf_structure" or "prompt_injection"
    severity: str      # "high" or "medium"
    detail: str        # human-readable explanation
    evidence: str | None = None  # the matched key or text snippet


@dataclass(slots=True)
class ScanResult:
    """The full outcome of scanning one PDF (structure) and its text (injection)."""

    source: str
    findings: list[SecurityFinding] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """True when nothing was flagged."""

        return not self.findings

    @property
    def max_severity(self) -> str | None:
        """The worst severity found, or None when clean."""

        if any(f.severity == "high" for f in self.findings):
            return "high"
        if any(f.severity == "medium" for f in self.findings):
            return "medium"
        return None


def scan_pdf_structure(pdf_path: Path) -> list[SecurityFinding]:
    """Walk every object in the PDF and flag active/executable content.

    We iterate the PDF object model with pikepdf instead of string-matching the
    raw bytes, because the object model sees the real structure and produces far
    fewer false positives. A malformed PDF that pikepdf cannot open is itself a
    finding, not a crash.
    """

    findings: list[SecurityFinding] = []
    try:
        with pikepdf.open(pdf_path) as pdf:
            # Every indirect object is inspected. A risky key can appear anywhere:
            # in the catalog, on a page, inside an annotation, or in names trees.
            for obj in pdf.objects:
                keys = _dictionary_keys(obj)
                for key in keys:
                    if key in RISKY_PDF_KEYS:
                        findings.append(
                            SecurityFinding(
                                category="pdf_structure",
                                severity=RISKY_PDF_KEYS[key],
                                detail=f"PDF contains active-content key {key}.",
                                evidence=key,
                            )
                        )
    except Exception as exc:  # noqa: BLE001 - any parse failure is a finding, not a crash
        findings.append(
            SecurityFinding(
                category="pdf_structure",
                severity="medium",
                detail="PDF could not be parsed cleanly; treat as suspicious.",
                evidence=str(exc)[:200],
            )
        )

    # De-duplicate: the same risky key often appears on many objects. One finding
    # per distinct key is enough to explain the risk.
    return _dedupe_findings(findings)


def scan_text_for_injection(text: str) -> list[SecurityFinding]:
    """Flag prompt-injection phrases in text that will be sent to the LLM."""

    findings: list[SecurityFinding] = []
    lowered = text.lower()
    for pattern in PROMPT_INJECTION_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            snippet = _context_snippet(text, match.start(), match.end())
            findings.append(
                SecurityFinding(
                    category="prompt_injection",
                    severity="high",
                    detail=f"Text matches injection pattern: {pattern!r}.",
                    evidence=snippet,
                )
            )
    return findings


def scan_pdf(pdf_path: Path, text: str | None = None) -> ScanResult:
    """Run both scans and return a combined result.

    Structure scanning always runs. Text scanning runs only when extracted text
    is provided, so the caller can scan after OCR when the real text exists.
    """

    result = ScanResult(source=pdf_path.name)
    result.findings.extend(scan_pdf_structure(pdf_path))
    if text:
        result.findings.extend(scan_text_for_injection(text))
    return result


def _dictionary_keys(obj: object) -> list[str]:
    """Return the dictionary keys of a pikepdf object, or empty for non-dicts."""

    try:
        return [str(key) for key in obj.keys()]
    except Exception:  # noqa: BLE001 - streams and scalars have no keys
        return []


def _dedupe_findings(findings: list[SecurityFinding]) -> list[SecurityFinding]:
    """Keep one finding per (category, evidence) pair."""

    seen: set[tuple[str, str | None]] = set()
    unique: list[SecurityFinding] = []
    for finding in findings:
        key = (finding.category, finding.evidence)
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return unique


def _context_snippet(text: str, start: int, end: int, window: int = 40) -> str:
    """Return the matched text plus a little surrounding context for the report."""

    left = max(0, start - window)
    right = min(len(text), end + window)
    return text[left:right].replace("\n", " ").strip()
