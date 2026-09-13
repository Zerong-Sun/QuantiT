"""qlib Alpha158 handler → ``qlib_cn`` dump research feature matrix.

Scope (honest)
--------------
This module wires ``qlib.contrib.data.handler.Alpha158`` to the local CSI300
dump and returns a date×instrument DataFrame for ``train_predict_ic``.
It is **not** a complete, gate-backed, or promotable Alpha158 trading system.
It does not change gate thresholds, does not auto-promote, and does not place
US/HK/CN orders. Paper booking stays on ``cl`` and still requires a gate pass.

No Alpha101 feature fallback
----------------------------
If pyqlib / the Alpha158 handler is missing, this module raises ImportError
(``pip install -e '.[closeloop]'``). It never substitutes Alpha101 columns.
The only shared Closeloop pieces are:

* label formula from ``build_dataset`` (``close[t+h]/close[t]-1``, not qlib LABEL0)
* the existing ``train_predict_ic`` consumer (date-fraction split, no embargo)
* panel instrument/date alignment via the qlib_cn dump / DataPlane

Design hooks (not applied in v1)
--------------------------------
* Feature available day **day+1** (PIT / no same-day peek):
  ``FEATURE_AVAILABLE_LAG_DAYS`` / ``apply_feature_available_lag``.
  ``build_alpha158_dataset`` calls the hook with ``lag=0``.
* Train/test **embargo**:
  ``TRAIN_EMBARGO_DAYS`` / ``apply_train_embargo``.
  Not called from the train CLI; ``train_predict_ic`` is unchanged.

Usage
-----
    from closeloop.model.alpha158 import build_alpha158_dataset
    from closeloop.model.train import train_predict_ic

    ds = build_alpha158_dataset("2020-01-01", "2024-12-31")
    train_predict_ic(ds)

Dump: ``~/.quantit/closeloop/qlib_cn`` (calendars / instruments / panel.parquet).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from closeloop.data.protocol import default_data_dir, field_frame
from closeloop.factors.ops import factor_stack

QLIB_INSTALL_HINT = "pip install -e '.[closeloop]'"
_DATE_ALIASES = {"date", "datetime", "time"}
_INST_ALIASES = {"instrument", "instruments", "asset", "symbol"}

# Intended PIT lag: handler bar on day t first usable on day t+1 (no same-day peek).
# v1 does not apply this; build_alpha158_dataset passes lag=0 into the hook.
FEATURE_AVAILABLE_LAG_DAYS = 1

# Intended gap (trading days) between last train date and first test date.
# v1 does not apply this; train_predict_ic still uses a contiguous date-fraction split.
TRAIN_EMBARGO_DAYS = 5


def apply_feature_available_lag(features: pd.DataFrame, *, lag: int = 0) -> pd.DataFrame:
    """PIT hook: intended ``lag=FEATURE_AVAILABLE_LAG_DAYS`` (day+1).

    TODO(PIT): when ``lag >= 1``, groupby instrument and ``shift(lag)`` so bar-t
    features are first indexed on day t+lag. Do not implement an Alpha101
    feature fallback here. v1 only accepts ``lag=0`` (same-day handler output).
    """
    if lag <= 0:
        return features
    raise NotImplementedError(
        "feature available-day lag is a design hook only; "
        "build_alpha158_dataset passes lag=0 (same-day Alpha158 bars)"
    )


def apply_train_embargo(dataset: pd.DataFrame, *, embargo_days: int = TRAIN_EMBARGO_DAYS) -> pd.DataFrame:
    """Train/test embargo hook. Not wired into ``train_predict_ic``.

    TODO(embargo): drop ``embargo_days`` between the last train date and the
    first test date so labels near the cut cannot leak. v1 leaves the shared
    trainer unchanged (contiguous split, no gap).
    """
    if embargo_days <= 0:
        return dataset
    raise NotImplementedError(
        "train embargo is a design hook only; train_predict_ic has no gap"
    )


def _qlib_missing() -> ImportError:
    return ImportError(
        "pyqlib is required to build Alpha158 datasets. "
        f"Install with: {QLIB_INSTALL_HINT}"
    )


def _import_qlib():
    try:
        import qlib
    except ImportError as exc:
        raise _qlib_missing() from exc
    return qlib


def _make_alpha158_handler(start: str, end: str, universe: str, **kwargs: Any):
    from qlib.contrib.data.handler import Alpha158

    params = {
        "instruments": universe,
        "start_time": start,
        "end_time": end,
        "fit_start_time": kwargs.pop("fit_start_time", start),
        "fit_end_time": kwargs.pop("fit_end_time", end),
    }
    params.update(kwargs)
    return Alpha158(**params)


def _flatten_feature_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if isinstance(out.columns, pd.MultiIndex):
        top = {str(v).lower() for v in out.columns.get_level_values(0)}
        if "label" in top:
            keep = [c for c in out.columns if str(c[0]).lower() != "label"]
            out = out.loc[:, keep]
        out.columns = [str(c[-1]) for c in out.columns]
    else:
        out.columns = [str(c) for c in out.columns]
    drop = [c for c in out.columns if str(c).upper().startswith("LABEL")]
    if drop:
        out = out.drop(columns=drop)
    return out


def _as_date_instrument(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame.index, pd.MultiIndex) or frame.index.nlevels != 2:
        raise ValueError("Alpha158 handler must return a date×instrument MultiIndex")
    names = [str(n).lower() if n else "" for n in frame.index.names]
    date_lvl = next((i for i, n in enumerate(names) if n in _DATE_ALIASES), None)
    inst_lvl = next((i for i, n in enumerate(names) if n in _INST_ALIASES), None)
    if date_lvl is None:
        date_lvl = 0
    if inst_lvl is None:
        inst_lvl = 1 - date_lvl
    out = frame
    if date_lvl != 0:
        out = out.swaplevel(0, 1)
    dates = pd.DatetimeIndex(pd.to_datetime(out.index.get_level_values(0)))
    insts = out.index.get_level_values(1).astype(str)
    out = out.copy()
    out.index = pd.MultiIndex.from_arrays([dates, insts], names=["date", "instrument"])
    return out.sort_index()


def _fetch_features(handler: Any) -> pd.DataFrame:
    try:
        raw = handler.fetch(col_set="feature")
    except TypeError:
        raw = handler.fetch()
    if raw is None or (hasattr(raw, "empty") and raw.empty):
        raw = handler.fetch()
    if raw is None or raw.empty:
        raise ValueError("Alpha158 handler returned no feature rows")
    return raw


def _forward_label(panel: pd.DataFrame, horizon: int) -> pd.Series:
    """Same t+horizon close return as ``build_dataset`` (future rows are NaN)."""
    close = field_frame(panel, "close")
    fwd = close.shift(-int(horizon)) / close - 1.0
    label = factor_stack(fwd)
    label.index.names = ["date", "instrument"]
    label.name = "label"
    return label


def _load_panel(start: str, end: str, data_dir: Path, universe: str) -> pd.DataFrame:
    from closeloop.data.qlib_cn import QlibCnDataPlane

    return QlibCnDataPlane(data_dir=data_dir, universe=universe).load_panel(start, end)


def build_alpha158_dataset(
    start: str,
    end: str,
    data_dir: Path | None = None,
    *,
    universe: str = "csi300",
    horizon: int = 1,
    handler: Any | None = None,
    panel: pd.DataFrame | None = None,
    **handler_kwargs: Any,
) -> pd.DataFrame:
    """Alpha158 handler features + Closeloop forward-return ``label``.

    Research matrix only. Not a promotable Alpha158 book. No Alpha101
    feature fallback (ImportError if pyqlib/handler is unavailable).

    Parameters
    ----------
    start, end:
        Inclusive sample window (passed to qlib ``Alpha158`` when ``handler``
        is omitted).
    data_dir:
        Qlib dump root. Defaults to ``~/.quantit/closeloop/qlib_cn``.
    universe:
        Instrument list name under ``instruments/`` (default ``csi300``).
    horizon:
        Label is ``close[t+horizon]/close[t] - 1`` — Closeloop train-path
        convention, **not** qlib ``LABEL0`` and not Alpha101 factor columns.
    handler:
        Optional object with ``fetch(...)`` (tests inject a mock). When omitted,
        pyqlib's ``Alpha158`` handler is constructed against ``data_dir``.
    panel:
        Closeloop field×instrument panel used to align names/dates and to
        build the label. Loaded from the dump when omitted.
    """
    dest = Path(data_dir) if data_dir is not None else default_data_dir()
    if handler is None:
        try:
            qlib = _import_qlib()
        except ImportError as exc:
            raise _qlib_missing() from exc
        qlib.init(provider_uri=str(dest), region="cn")
        try:
            handler = _make_alpha158_handler(start, end, universe, **handler_kwargs)
        except ImportError as exc:
            raise _qlib_missing() from exc
    if panel is None:
        panel = _load_panel(start, end, dest, universe)

    features = _as_date_instrument(_flatten_feature_columns(_fetch_features(handler)))
    allowed = set(field_frame(panel, "close").columns.astype(str))
    features = features.loc[features.index.get_level_values("instrument").isin(allowed)]
    panel_dates = set(pd.DatetimeIndex(panel.index))
    features = features.loc[features.index.get_level_values("date").isin(panel_dates)]
    # PIT hook is present; lag=0 means same-day bars (day+1 not applied in v1).
    features = apply_feature_available_lag(features, lag=0)
    label = _forward_label(panel, horizon)
    out = features.join(label, how="left")
    if "label" not in out.columns:
        out["label"] = label.reindex(out.index)
    return out
