"""
Split a parsed receipt into per-category amounts (one expense per category on mixed baskets).

Item-level adjustments (member discount, multi-buy) go to the category of the item(s) they apply to,
prorated by item price when they span categories. Whole-bill adjustments (vouchers, points, rounding,
bag charge) and any unexplained difference to the total are prorated across categories.
Splits always sum to the receipt total.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_CENT = Decimal("0.01")


def _dec(value) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def split_receipt(total: Decimal | None, category: str | None, items: list, adjustments: list) -> tuple[list[dict], Decimal | None]:
    """Return (splits, unexplained). Each split is {category, amount, items}; unexplained is the difference
    between the total and the printed lines (None when zero or not computable)."""
    lines = [(it, _dec(it.get("amount"))) for it in items if isinstance(it, dict)]
    lines = [(it, amt) for it, amt in lines if amt is not None]
    whole = [{"category": category, "amount": total, "items": [str(it.get("name")) for it, _ in lines]}]
    if total is None or not lines:
        return whole, None

    net = [amt for _, amt in lines]
    whole_bill = Decimal(0)
    for adj in adjustments:
        amount = _dec(adj.get("amount")) if isinstance(adj, dict) else None
        if amount is None:
            continue
        idx = [i for i in (adj.get("applies_to") or []) if isinstance(i, int) and 0 <= i < len(lines)]
        base = sum(lines[i][1] for i in idx)
        if idx and base > 0:
            for i in idx:
                net[i] += amount * lines[i][1] / base
        else:
            whole_bill += amount

    by_cat: dict[str | None, Decimal] = {}
    names: dict[str | None, list[str]] = {}
    for (it, _), amount in zip(lines, net):
        cat = it.get("category") or category
        by_cat[cat] = by_cat.get(cat, Decimal(0)) + amount
        names.setdefault(cat, []).append(str(it.get("name")))

    gross = sum(by_cat.values())
    if gross <= 0:
        return whole, None
    unexplained = total - gross - whole_bill
    spread = whole_bill + unexplained
    amounts = {cat: (v + spread * v / gross).quantize(_CENT, ROUND_HALF_UP) for cat, v in by_cat.items()}
    amounts = {cat: v for cat, v in amounts.items() if v > 0} or {category: total}  # fully discounted lines
    # rounding cents go to the largest category so splits sum exactly to the total
    largest = max(amounts, key=amounts.get)
    amounts[largest] += total - sum(amounts.values())

    splits = [{"category": cat, "amount": amounts[cat], "items": names.get(cat, [])}
              for cat in sorted(amounts, key=amounts.get, reverse=True)]
    unexplained = unexplained.quantize(_CENT, ROUND_HALF_UP)
    return splits, (unexplained or None)
