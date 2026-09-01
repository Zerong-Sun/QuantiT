"""Persisted notes for the paper terminal."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from quantit.paper.models import Note

NOTE_MAX_LEN = 4000


class NoteBook:
    """Single-user note list stored next to paper trades."""

    def __init__(self, session: Session, now: Callable[[], datetime] | None = None) -> None:
        self.session = session
        self._now = now or datetime.utcnow

    def list_notes(self, market_id: str | None = None, symbol: str | None = None) -> list[Note]:
        q = self.session.query(Note).order_by(Note.id.desc())
        if market_id:
            q = q.filter_by(market_id=market_id)
        if symbol:
            q = q.filter_by(symbol=symbol)
        return list(q.all())

    def add_note(
        self,
        body: str,
        market_id: str | None = None,
        symbol: str | None = None,
    ) -> Note:
        text = (body or "").strip()
        if not text:
            raise ValueError("note body is empty")
        if len(text) > NOTE_MAX_LEN:
            raise ValueError(f"note body exceeds {NOTE_MAX_LEN} characters")
        note = Note(
            body=text,
            market_id=market_id or None,
            symbol=symbol or None,
            created_at=self._now(),
        )
        self.session.add(note)
        self.session.commit()
        return note

    def delete_note(self, note_id: int) -> None:
        note = self.session.query(Note).filter_by(id=note_id).one_or_none()
        if note is None:
            raise KeyError(f"note {note_id} not found")
        self.session.delete(note)
        self.session.commit()
