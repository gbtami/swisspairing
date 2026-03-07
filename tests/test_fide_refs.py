"""Unit tests for pinned FIDE reference constants."""

from swisspairing.fide_refs import FIDE_C0401_2026, FIDE_C0402_2026, FIDE_C0403_2026


def test_fide_reference_constants_are_https_urls() -> None:
    refs = (FIDE_C0401_2026, FIDE_C0402_2026, FIDE_C0403_2026)
    assert all(ref.startswith("https://handbook.fide.com/chapter/") for ref in refs)
