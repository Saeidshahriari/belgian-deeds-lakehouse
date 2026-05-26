"""Focused tests for the extraction schema contract."""

from pydantic import ValidationError

from sagora_deeds.schemas import DocumentExtraction, GeminiExtraction


def test_document_extraction_accepts_nested_payload() -> None:
    """DocumentExtraction should accept the pipeline-owned validated artifact."""

    payload = {
        "source_file": "sample.pdf",
        "page_count": 2,
        "ocr_used": True,
        "source_type": "scan",
        "deeds": [
            {
                "extracted_enterprise_number": " 0500708654 ",
                "deed_type": "incorporation",
                "deed_date": "8 November 2012",
                "publication_date": "19 November 2012",
                "publication_reference": "20121119-1234",
                "form_reference": "Volet B",
                "language": "nl",
                "summary": "Company incorporation notice.",
                "companies": [
                    {
                        "enterprise_number": "0500708654",
                        "company_name": "Future At Work",
                        "legal_form": "BVBA",
                    }
                ],
                "party_roles": [
                    {
                        "name": "VAN DESSEL Steven",
                        "party_type": "person",
                        "role": "founder",
                        "confidence": 0.9,
                    }
                ],
            }
        ],
    }

    parsed = DocumentExtraction.model_validate(payload)

    assert parsed.page_count == 2
    assert parsed.source_type == "scan"
    assert parsed.deeds[0].extracted_enterprise_number == "0500708654"
    assert parsed.deeds[0].companies[0].company_name == "Future At Work"


def test_gemini_extraction_rejects_pipeline_metadata() -> None:
    """GeminiExtraction should contain only LLM-extracted deed data."""

    try:
        GeminiExtraction.model_validate(
            {
                "source_file": "sample.pdf",
                "page_count": 2,
                "ocr_used": True,
                "deeds": [],
            }
        )
    except ValidationError:
        return
    raise AssertionError("GeminiExtraction accepted pipeline metadata.")
