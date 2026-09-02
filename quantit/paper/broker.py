"""Persisted paper broker: market orders at the last delayed quote."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from quantit.markets.assets import allowed_list, asset_class, is_allowed, multiplier
from quantit.markets.registry import MarketRegistry, get_registry
from quantit.paper.capital import PAPER_CASH
from quantit.paper.models import Account, Order, Position, PositionLot, Trade


class PaperBroker:
    """Single-user paper trading across registered markets."""

    def __init__(
        self,
        session: Session,
        registry: MarketRegistry | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self.registry = registry or get_registry()
        self._now = now or datetime.utcnow

    def now(self) -> datetime:
        return self._now()

    def ensure_accounts(self, cash: float | dict[str, float] | None = None) -> None:
        if cash is None:
            targets = dict(PAPER_CASH)
        elif isinstance(cash, dict):
            targets = dict(PAPER_CASH)
            targets.update(cash)
        else:
            targets = {adapter.market_id: float(cash) for adapter in self.registry.all()}

        existing = {a.market_id: a for a in self.list_accounts()}
        for adapter in self.registry.all():
            target = targets.get(adapter.market_id, PAPER_CASH.get(adapter.market_id, 100_000.0))
            account = existing.get(adapter.market_id)
            if account is None:
                self.session.add(
                    Account(
                        market_id=adapter.market_id,
                        currency=adapter.profile.currency,
                        cash=target,
                        initial_cash=target,
                    )
                )
                continue
            idle = account.cash == account.initial_cash and not any(
                p.quantity > 0 for p in account.positions
            )
            delta = target - account.initial_cash
            if abs(delta) <= 1e-6:
                continue
            if idle:
                account.cash = target
                account.initial_cash = target
            else:
                # Resize the paper endowment without flattening open positions.
                account.cash += delta
                account.initial_cash = target
        self.session.commit()

    def list_accounts(self) -> list[Account]:
        return list(self.session.query(Account).order_by(Account.market_id).all())

    def get_account(self, market_id: str) -> Account:
        account = self.session.query(Account).filter_by(market_id=market_id).one_or_none()
        if account is None:
            raise KeyError(f"No paper account for market {market_id}")
        return account

    def list_orders(self, market_id: str | None = None) -> list[Order]:
        q = self.session.query(Order).order_by(Order.id.desc())
        if market_id:
            q = q.filter_by(market_id=market_id)
        return list(q.all())

    def list_trades(self, market_id: str | None = None) -> list[Trade]:
        q = self.session.query(Trade).order_by(Trade.id.desc())
        if market_id:
            q = q.filter_by(market_id=market_id)
        return list(q.all())

    def list_positions(self, market_id: str | None = None) -> list[Position]:
        q = self.session.query(Position).filter(Position.quantity > 0)
        if market_id:
            q = q.filter_by(market_id=market_id)
        return list(q.all())

    def get_position(self, market_id: str, symbol: str) -> Position | None:
        adapter = self.registry.get(market_id)
        canonical = adapter.normalize_symbol(symbol)
        pos = (
            self.session.query(Position)
            .filter_by(market_id=market_id, symbol=canonical)
            .one_or_none()
        )
        if pos is not None and pos.quantity <= 0:
            return None
        return pos

    def place_order(
        self,
        market_id: str,
        symbol: str,
        side: str,
        quantity: int,
        rationale: str | None = None,
    ) -> Order:
        adapter = self.registry.get(market_id)
        canonical = adapter.normalize_symbol(symbol)
        side = side.lower()
        ts = self.now()
        account = self.get_account(market_id)
        order = Order(
            account_id=account.id,
            market_id=market_id,
            symbol=canonical,
            side=side,
            quantity=quantity,
            status="pending",
            rationale=(rationale.strip() or None) if rationale else None,
            created_at=ts,
        )
        self.session.add(order)
        self.session.flush()

        if side not in {"buy", "sell"}:
            return self._reject(order, f"unsupported side: {side}")

        klass = asset_class(market_id, canonical)
        if not is_allowed(market_id, canonical):
            return self._reject(
                order,
                f"{klass} is not enabled for {market_id} paper (allowed: {', '.join(allowed_list(market_id))})",
            )
        mult = multiplier(market_id, canonical)

        qty_errors = adapter.validate_quantity(canonical, quantity)
        if qty_errors:
            return self._reject(order, "; ".join(qty_errors))

        try:
            quote = adapter.fetch_quote(canonical)
        except (ValueError, KeyError) as exc:
            return self._reject(order, f"no quote: {exc}")

        if quote.last <= 0:
            return self._reject(order, "no quote: last price is not positive")

        slip = quote.last * adapter.profile.slippage_rate
        fill_price = quote.last + slip if side == "buy" else quote.last - slip
        if market_id == "cn":
            rate = adapter.profile.commission_rate
            if klass == "equity" and side == "sell":
                rate += adapter.profile.stamp_duty_rate
        else:
            rate = adapter.profile.all_in_commission_rate
        commission = fill_price * quantity * mult * rate

        if side == "buy":
            cost = fill_price * quantity * mult + commission
            if cost > account.cash:
                return self._reject(order, f"insufficient cash: need {cost:.2f}, have {account.cash:.2f}")
            account.cash -= cost
            pos = self._get_or_create_position(account, market_id, canonical)
            total = pos.avg_cost * pos.quantity + fill_price * quantity
            pos.quantity += quantity
            pos.avg_cost = total / pos.quantity
            self.session.add(
                PositionLot(
                    position_id=pos.id,
                    quantity=quantity,
                    remaining=quantity,
                    price=fill_price,
                    acquired_on=ts,
                )
            )
        else:
            pos = self.get_position(market_id, canonical)
            held = pos.quantity if pos is not None else 0
            if quantity > held:
                return self._reject(order, f"insufficient shares: need {quantity}, have {held} (no shorting)")
            sellable = self._sellable_qty(pos, ts, adapter.t_plus)
            if quantity > sellable:
                return self._reject(
                    order,
                    f"T+{adapter.t_plus} restriction: only {sellable} shares sellable today",
                )
            proceeds = fill_price * quantity * mult - commission
            account.cash += proceeds
            self._consume_lots(pos, quantity, ts, adapter.t_plus)
            pos.quantity -= quantity
            if pos.quantity == 0:
                pos.avg_cost = 0.0

        order.status = "filled"
        order.fill_price = fill_price
        order.commission = commission
        order.fill_time = ts
        self.session.add(
            Trade(
                order_id=order.id,
                account_id=account.id,
                market_id=market_id,
                symbol=canonical,
                side=side,
                quantity=quantity,
                price=fill_price,
                commission=commission,
                timestamp=ts,
            )
        )
        self.session.commit()
        return order

    def _reject(self, order: Order, reason: str) -> Order:
        order.status = "rejected"
        order.reject_reason = reason
        self.session.commit()
        return order

    def _get_or_create_position(self, account: Account, market_id: str, symbol: str) -> Position:
        pos = (
            self.session.query(Position)
            .filter_by(account_id=account.id, symbol=symbol)
            .one_or_none()
        )
        if pos is None:
            pos = Position(
                account_id=account.id,
                market_id=market_id,
                symbol=symbol,
                quantity=0,
                avg_cost=0.0,
            )
            self.session.add(pos)
            self.session.flush()
        return pos

    def _sellable_qty(self, pos: Position, now: datetime, t_plus: int) -> int:
        if t_plus <= 0:
            return pos.quantity
        cutoff = now.date()
        total = 0
        for lot in pos.lots:
            if lot.remaining <= 0:
                continue
            held_days = (cutoff - lot.acquired_on.date()).days
            if held_days >= t_plus:
                total += lot.remaining
        return total

    def _consume_lots(self, pos: Position, quantity: int, now: datetime, t_plus: int) -> None:
        remaining = quantity
        lots = sorted(pos.lots, key=lambda lot: lot.acquired_on)
        for lot in lots:
            if remaining <= 0:
                break
            if lot.remaining <= 0:
                continue
            if t_plus > 0:
                held_days = (now.date() - lot.acquired_on.date()).days
                if held_days < t_plus:
                    continue
            take = min(lot.remaining, remaining)
            lot.remaining -= take
            remaining -= take
        if remaining > 0:
            raise ValueError("not enough sellable lots")
