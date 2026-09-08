"""Paper books: one cash account per strategy, sharing a venue adapter.

``book_id`` is persisted on accounts/orders. Quotes, lots, and asset-class
rules use ``venue`` (``us`` / ``hk`` / ``cn`` / ``cl``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaperBook:
    book_id: str
    venue: str
    strategy_id: str
    cash: float
    label: str
    currency: str


PAPER_BOOKS: tuple[PaperBook, ...] = (
    PaperBook("us", "us", "tsmom", 100_000.0, "US quality TSMOM", "USD"),
    PaperBook("us_book", "us", "us_book", 100_000.0, "US MA/RSI", "USD"),
    PaperBook("hk", "hk", "hk_quality_book", 1_000_000.0, "HK quality TSMOM", "HKD"),
    PaperBook("hk_theme", "hk", "theme_rotation", 1_000_000.0, "HK HSTECH rotation", "HKD"),
    PaperBook("cn", "cn", "cn_quality_book", 1_000_000.0, "CN quality TSMOM", "CNY"),
    PaperBook("cn_etf", "cn", "cn_etf_rotation", 1_000_000.0, "CN industry ETF", "CNY"),
    PaperBook("cl", "cl", "closeloop", 1_000_000.0, "Closeloop CSI300", "CNY"),
)

_BY_ID: dict[str, PaperBook] = {book.book_id: book for book in PAPER_BOOKS}

PAPER_CASH: dict[str, float] = {book.book_id: book.cash for book in PAPER_BOOKS}

DESK_BOOK_IDS: tuple[str, ...] = tuple(book.book_id for book in PAPER_BOOKS if book.book_id != "cl")

_VENUE_ALIAS: dict[str, str] = {book.book_id: book.venue for book in PAPER_BOOKS}


def get_book(book_id: str) -> PaperBook | None:
    return _BY_ID.get(book_id)


def venue_of(book_id: str) -> str:
    """Venue adapter id for a book (unknown ids are treated as venues)."""
    raw = (book_id or "").strip()
    if not raw:
        return raw
    return _VENUE_ALIAS.get(raw, raw)


def desk_books() -> tuple[PaperBook, ...]:
    return tuple(book for book in PAPER_BOOKS if book.book_id != "cl")
