"""Solar generation offset (光伏电量抵扣).

Fixed billing order, by contract:

  1. deduct the solar offset from gross usage -> net usage, floored at zero;
  2. split the NET usage into progressive tiers;
  3. apply the peak factor last, to every segmented amount.

The factor never changes the tier boundaries — it only multiplies the already
segmented amounts, so gross / offset / net and every segment stay auditable.
"""

from app.engines.helpers import kwh_qty, money


def apply_offset(gross_kwh: float, offset_kwh: float) -> dict:
    """Step 1: net = max(0, gross - offset). Returns applied vs requested."""
    gross = max(0.0, float(gross_kwh))
    requested = max(0.0, float(offset_kwh))
    applied = min(gross, requested)
    return {
        "gross_kwh": kwh_qty(gross),
        "offset_kwh": kwh_qty(applied),
        "net_kwh": kwh_qty(gross - applied),
    }


def _segment_net(net_kwh: float, tiers: list[dict]) -> list[dict]:
    """Step 2: progressive bands over NET usage, priced at the base rate (factor 1)."""
    remain = float(net_kwh)
    segments = []
    prev = 0.0
    for t in tiers:
        up = t.get("up_to")
        base_price = float(t["price"])
        if up is None:
            qty = remain
        else:
            span = float(up) - prev
            qty = min(remain, max(0.0, span))
        if qty > 1e-9:
            segments.append(
                {
                    "from_kwh": prev,
                    "to_kwh": prev + qty,
                    "qty": qty,
                    "base_price": round(base_price, 4),
                }
            )
            remain -= qty
        if up is not None:
            prev = float(up)
        if remain <= 1e-9:
            break
    return segments


def calc_bill_with_offset(
    gross_kwh: float,
    offset_kwh: float,
    tiers: list[dict],
    peak_factor: float = 1.0,
) -> dict:
    """Full pipeline. ``tiers`` is [{up_to, price}], last ``up_to`` may be None."""
    head = apply_offset(gross_kwh, offset_kwh)
    pf = float(peak_factor)

    segments = []
    total = 0.0
    # Steps 2 then 3: segment the net first, multiply by the peak factor last.
    for seg in _segment_net(head["net_kwh"], tiers):
        qty = seg["qty"]
        price = round(seg["base_price"] * pf, 4)
        amount = money(qty * seg["base_price"] * pf)
        total += amount
        segments.append(
            {
                "from_kwh": seg["from_kwh"],
                "to_kwh": seg["to_kwh"],
                "qty": kwh_qty(qty),
                "base_price": seg["base_price"],
                "factor": pf,
                "price": price,
                "amount": amount,
            }
        )

    return {
        "gross_kwh": head["gross_kwh"],
        "offset_kwh": head["offset_kwh"],
        "net_kwh": head["net_kwh"],
        "peak_factor": pf,
        "segments": segments,
        "total": money(total),
    }
