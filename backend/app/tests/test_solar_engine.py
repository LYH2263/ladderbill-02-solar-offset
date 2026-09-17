from app.modules.solar_offset import apply_offset, calc_bill_with_offset

TIERS = [
    {"up_to": 180, "price": 0.52},
    {"up_to": 260, "price": 0.62},
    {"up_to": None, "price": 0.82},
]


def test_offset_deducted_before_tiers():
    # 400 - 200 = 200 net; only the net is tier-segmented.
    r = calc_bill_with_offset(400, 200, TIERS, 1.0)
    assert r["gross_kwh"] == 400
    assert r["offset_kwh"] == 200
    assert r["net_kwh"] == 200
    # 180 @ 0.52 + 20 @ 0.62 = 93.60 + 12.40
    assert r["total"] == 106.00
    assert [(s["from_kwh"], s["to_kwh"], s["qty"]) for s in r["segments"]] == [
        (0.0, 180.0, 180.0),
        (180.0, 200.0, 20.0),
    ]


def test_net_floored_at_zero_when_offset_exceeds_gross():
    r = calc_bill_with_offset(100, 150, TIERS, 1.0)
    assert r["gross_kwh"] == 100
    assert r["offset_kwh"] == 100          # only the available gross can be deducted
    assert r["net_kwh"] == 0
    assert r["segments"] == []
    assert r["total"] == 0


def test_zero_offset_is_plain_tiered_bill():
    r = calc_bill_with_offset(400, 0, TIERS, 1.0)
    assert r["offset_kwh"] == 0
    assert r["net_kwh"] == 400
    assert r["total"] == 258.00


def test_peak_factor_applied_last_to_segmented_net():
    plain = calc_bill_with_offset(400, 200, TIERS, 1.0)
    peak = calc_bill_with_offset(400, 200, TIERS, 1.2)
    # Factor multiplies amounts; it never moves the net-based boundaries.
    assert peak["total"] == round(plain["total"] * 1.2, 2)
    assert [s["qty"] for s in peak["segments"]] == [s["qty"] for s in plain["segments"]]
    assert all(s["factor"] == 1.2 for s in peak["segments"])
    # 180*0.52*1.2 + 20*0.62*1.2
    assert peak["segments"][0]["amount"] == 112.32
    assert peak["segments"][1]["amount"] == 14.88
    assert peak["total"] == 127.20


def test_factor_does_not_change_boundaries_even_across_tier():
    # 150 net sits entirely in the first band; factor must not push it into a higher tier.
    r = calc_bill_with_offset(200, 50, TIERS, 1.2)
    assert r["net_kwh"] == 150
    assert len(r["segments"]) == 1
    assert r["segments"][0]["to_kwh"] == 150.0
    assert r["total"] == 93.60


def test_apply_offset_reports_applied_vs_requested():
    h = apply_offset(120.5, 300)
    assert h == {"gross_kwh": 120.5, "offset_kwh": 120.5, "net_kwh": 0.0}
