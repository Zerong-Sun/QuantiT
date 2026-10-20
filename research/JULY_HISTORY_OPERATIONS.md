# July-start isolated daily paper histories

The `/history` page compares 6 desk strategies and 5 frozen research strategies from 2026-07-01. It records each market session, including days with no trades, using previous-session signals and next-opening-price fills. It does not open the active `paper.db` and never sends brokerage orders.

The dynamic Alpha101/Closeloop research account is separate from these 11 fixed strategies. Its current factor library is not used as a historical July selection record. This replay does not reconstruct that research worker's point-in-time factor-selection process.

## Execution contract

Each US book starts at USD 100,000; each HK/CN book starts at HKD/CNY 1,000,000. All books are independent. ML models are the last eligible training folds before July (April 2026 training cutoffs); do not replace them with October-trained `latest.txt`. Rules and model portfolio settings are frozen in `protocol.json`. The initial portfolio is empty. Five research strategies rebalance every five CN sessions, anchored to the first simulated session. Their chosen top-K counts are 20/10/10/10/20 for h1/h5/h10/momentum20/momentum60.

Fees use venue commission/stamp duty plus 5 bps price slippage each way, with HKD 18/CNY 5 minimum commissions. HK/CN ETFs are exempt from the simulated stock stamp duty. These are explicit simplified assumptions, not an exact brokerage tariff. Each symbol is capped at 1% of the prior session's share volume. CN uses T+1 and board lots, with a conservative 200-share STAR rule. Price-limit proxies are 9.5%/19.5%, not a point-in-time reconstruction of ST/IPO rules or order queues. Partial lots created by corporate actions can exit in full.

Stock/ETF dividends become receivables included in equity, not immediately reusable cash; actual payment dates and personal taxes are not modeled. Splits adjust position lots before trading. A suspended position remains held and is marked from available data with an explicit estimate flag. Options and warrants are excluded because reliable historical contract chains were unavailable. Fixed present-day universes and the current rule version introduce historical selection limitations; this is a retrospective simulation, not proof of live profitability.

## Durable data and evidence

Default root: `~/.quantit/history/2026-07-01/`.

- `books/{strategy}.db`: isolated SQLite ledger and complete day details.
- `feeds/{snapshot}/manifest.json`: source/hash/coverage/cross-check evidence and raw files.
- `signals/{snapshot}/manifest.json`: frozen model identity, eligible training dates and prediction hashes.
- `protocol.json`, `parameters.yaml`: immutable execution/parameter contract.
- `report.json`: atomic frontend export; per-strategy files also persist the daily equity series.
- `service-config.json`, `cycle.json`, `service.json`: configuration, last completed closing window and heartbeat.
- `attempt-01-before-boundary-fixes/`, `attempt-02-before-source-validation/`: rejected preliminary attempts, retained for audit and excluded from the final report.

A whole day executes in a disposable database copy. Only successful completion replaces the durable account. Repeating a completed history does not create additional orders. A root lock prevents simultaneous runs. An error in one strategy leaves other books available. A changed frozen execution contract raises an error and requires a separate history experiment; never edit its hash to bypass the check.

## Source validation

Yahoo `auto_adjust=False` still expresses historical prices in split-adjusted units. The executor restores nominal prices before applying share entitlements. Known missing ETF actions are in `quantit/paper/history_actions.json`, with issuer announcements for 512480 (2026-07-03), 159995 (2026-07-07) and 159813 (2026-08-03), all 1:2 splits. Those instruments use independent Tencent nominal bars, converted into the bundle convention with explicit action records. Original Yahoo frames remain under `source/`.

Latest CN OHLC is independently checked against Tencent, because the source can combine a stale opening price with a current closing price. Volumes and other action fields retain their documented source. A zero-volume suspended series can retain the independently matching last traded close. Unexplained large CN gaps, missing feeds and invalid prices block affected strategies. Inconsistent OHLC high/low envelopes are visible warnings, not automatic guessed repairs. Market calendars come from actual reference-bar dates; only already closed sessions are executed.

## Re-run the existing snapshot

From the repository checkout, with the environments and snapshots already prepared:

```sh
.venv/bin/python -m quantit.paper.history \
  --root "$HOME/.quantit/history/2026-07-01" \
  --feed "$HOME/.quantit/history/2026-07-01/feeds/2026-10-20-verified" \
  --signals "$HOME/.quantit/history/2026-07-01/signals/2026-10-20" \
  --start 2026-07-01 --end 2026-10-20
```

The research environment is Python 3.11 with Qlib/LightGBM; this checkout's paper/API environment is `.venv`. Prices and model files are local artifacts, not committed to Git. The daily downloader is `quantit.paper.history_data.download`; the model exporter is `python -m closeloop.model.history_signals --help`.

Run `.venv/bin/python scripts/check_history_ledger.py` to independently reconcile every day's cash flows, corporate actions, positions, fees, returns, exports and final position lots. Compare its logical ledger hashes before and after a repeat run to verify idempotence. The checker explicitly stops on fractional-share split entitlements that require a separate lot-level audit.

## Ongoing continuation

`service-config.json` names `start`, `source_data` (the original Qlib dump), `experiment` (the original trained experiment) and `signals` (the initial historical signal snapshot). `scripts/run_history_service.py --once` performs one eligible continuation cycle; the default is resident mode. After one validated complete replay:

```sh
.venv311/bin/python scripts/run_history_service.py --once
.venv/bin/python scripts/install_history_service.py
launchctl print "gui/$(id -u)/com.quantit.history"
```

The launch agent is `com.quantit.history`, distinct from `com.quantit.paper`. It checks closing windows every ten minutes, waits until one hour after regular closes for fresh data, and retries failures hourly. It refreshes the fixed CN universe, applies the same frozen model, and appends days. If feature refresh fails, rule books can still advance; model failures remain visible and retryable. Successful repeated closing windows avoid network downloads. The daemon updates a heartbeat, handles shutdown, and launchd restarts it after exit. It requires this Mac to be awake, logged in and online; it does not imply cloud hosting.

Use `/api/v1/history` for the report and `/api/v1/history/{strategy}/{YYYY-MM-DD}` for a read-only daily ledger. A heartbeat older than one hour is shown as unconfirmed. Errors are recorded in `service.json`, `service.log`, and `worker.log`. Do not delete a failed day or fabricate missing market data to make the status green.
