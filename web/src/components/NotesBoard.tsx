import { useState, type FormEvent } from "react";
import type { Note } from "../types";

const NOTE_MAX = 4000;

export function NotesBoard({
  notes,
  market,
  symbol,
  onAdd,
  onDelete,
}: {
  notes: Note[];
  market: string;
  symbol: string;
  onAdd: (body: string, tagSymbol: boolean) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}) {
  const [draft, setDraft] = useState("");
  const [tagSymbol, setTagSymbol] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim() || busy) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onAdd(draft, tagSymbol);
      setDraft("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="notes-board">
      <form className="note-compose" onSubmit={submit}>
        <textarea
          value={draft}
          maxLength={NOTE_MAX}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Trade journal, thesis, reminder…"
          rows={3}
        />
        <div className="note-actions">
          <label>
            <input type="checkbox" checked={tagSymbol} onChange={(e) => setTagSymbol(e.target.checked)} />
            Tag {symbol} ({market.toUpperCase()})
          </label>
          <button type="submit" disabled={busy || !draft.trim()}>
            Post
          </button>
        </div>
        {error ? <p className="banner error">{error}</p> : null}
      </form>
      <ul className="note-list">
        {notes.length === 0 ? (
          <li className="empty">No notes yet.</li>
        ) : (
          notes.map((n) => (
            <li key={n.id}>
              <div className="note-head">
                <span>{n.created_at.replace("T", " ").slice(0, 19)}</span>
                {n.symbol ? (
                  <span className="tag">
                    {(n.market_id ?? "").toUpperCase()} {n.symbol}
                  </span>
                ) : null}
                <button type="button" className="ghost" onClick={() => onDelete(n.id)}>
                  Delete
                </button>
              </div>
              <p>{n.body}</p>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}
