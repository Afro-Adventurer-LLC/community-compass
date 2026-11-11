from app.services.index import canonical_doc_id


def test_canonical_doc_id_maps_bedrock_s3_uri():
    assert (
        canonical_doc_id(
            "s3://abw-connect-kb-000000000000/kb/official/2026/abw-terms.md#4"
        )
        == "official/2026/abw-terms"
    )
    assert canonical_doc_id("official/2026/faqs-accessibility") == "official/2026/faqs-accessibility"
    assert canonical_doc_id("kb/official/2026/accessibility-services.md") == "official/2026/accessibility-services"


def test_local_index_doc_text_accepts_s3_uri(index):
    text = index.doc_text("s3://abw-connect-kb/kb/official/2026/abw-terms.md")
    assert "21 years of age" in text
    assert "Hotel accommodations" in text
    faq = index.doc_text("s3://bucket/kb/official/2026/faqs-accessibility.md#1")
    assert "November 14th" in faq
