def verify_quote_provenance(quote: str, source_text: str) -> bool:
    """Check that quote is an exact, contiguous substring of its sanitized source review."""
    if not quote or not source_text:
        return False
    return quote in source_text
