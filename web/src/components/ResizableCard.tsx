import { useCallback, useState, type CSSProperties, type PointerEvent, type ReactNode } from "react";

const STORAGE_KEY = "quantit-card-sizes";

type Size = { w: number; h: number };

function readSizes(): Record<string, Size> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Record<string, Size>) : {};
  } catch {
    return {};
  }
}

function writeSize(id: string, w: number, h: number) {
  const all = readSizes();
  all[id] = { w: Math.round(w), h: Math.round(h) };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
}

export function ResizableCard({
  id,
  title,
  className = "",
  loading = false,
  children,
  minWidth = 220,
  minHeight = 140,
}: {
  id: string;
  title?: string;
  className?: string;
  loading?: boolean;
  children: ReactNode;
  minWidth?: number;
  minHeight?: number;
}) {
  const [size, setSize] = useState<Partial<Size>>(() => readSizes()[id] ?? {});

  const onGripDown = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      event.stopPropagation();
      const grip = event.currentTarget;
      const card = grip.parentElement;
      if (!card) {
        return;
      }
      grip.setPointerCapture(event.pointerId);
      const rect = card.getBoundingClientRect();
      const start = { x: event.clientX, y: event.clientY, w: rect.width, h: rect.height };
      let next = { w: start.w, h: start.h };
      const onMove = (ev: globalThis.PointerEvent) => {
        next = {
          w: Math.max(minWidth, start.w + ev.clientX - start.x),
          h: Math.max(minHeight, start.h + ev.clientY - start.y),
        };
        setSize(next);
      };
      const onUp = () => {
        grip.removeEventListener("pointermove", onMove);
        grip.removeEventListener("pointerup", onUp);
        grip.removeEventListener("pointercancel", onUp);
        writeSize(id, next.w, next.h);
      };
      grip.addEventListener("pointermove", onMove);
      grip.addEventListener("pointerup", onUp);
      grip.addEventListener("pointercancel", onUp);
    },
    [id, minWidth, minHeight],
  );

  const sized = size.w != null && size.h != null;
  const style: CSSProperties = {
    minWidth,
    minHeight,
    width: size.w,
    height: size.h,
    ...(sized ? { flexGrow: 0, flexShrink: 0, flexBasis: "auto" } : {}),
  };

  return (
    <section
      className={`card ${className} ${size.w || size.h ? "is-sized" : ""}`.trim()}
      style={style}
      data-card={id}
    >
      {title ? (
        <header className="card-head">
          <h2>{title}</h2>
          {loading ? <span className="spinner" aria-label="loading" /> : null}
        </header>
      ) : null}
      <div className="card-body">
        {loading ? (
          <div className="card-loading" aria-busy="true">
            <span className="spinner lg" />
          </div>
        ) : null}
        {children}
      </div>
      <div className="card-grip" title="Drag to resize" onPointerDown={onGripDown} />
    </section>
  );
}
