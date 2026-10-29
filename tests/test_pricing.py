"""US16 / #135: expected prices come from the promotion contract, not the service."""

import pytest

from src.services.pricing import (
    ItemDiscount,
    PricingLine,
    ShippingDiscount,
    calculate_item_discount,
)


@pytest.mark.parametrize(
    "rule,basis,expected",
    [
        (ItemDiscount("FIXED_AMOUNT", 50_000), 40_000, 40_000),
        (ItemDiscount("FIXED_AMOUNT", 50_000), 50_000, 50_000),
        (ItemDiscount("FIXED_AMOUNT", 50_000), 50_001, 50_000),
        (ItemDiscount("FIXED_AMOUNT", 1), 0, 0),
        (ItemDiscount("PERCENTAGE", 1500, 20_000), 300_000, 20_000),
        (ItemDiscount("PERCENTAGE", 333), 10_001, 333),
        (ItemDiscount("PERCENTAGE", 1), 9_999, 0),
        (ItemDiscount("PERCENTAGE", 1), 10_000, 1),
        (ItemDiscount("PERCENTAGE", 10_000), 12_345, 12_345),
        (ItemDiscount("PERCENTAGE", 10_000, 99_999), 1, 1),
    ],
)
def test_item_discount_boundaries(rule, basis, expected):
    assert calculate_item_discount(rule, basis) == expected


@pytest.mark.parametrize(
    "kind,value,cap",
    [
        ("PERCENTAGE", 0, None),
        ("PERCENTAGE", 10_001, None),
        ("FIXED_AMOUNT", 0, None),
        ("FIXED_AMOUNT", -1, None),
        ("PERCENTAGE", 1000, 0),
        ("PERCENTAGE", 1000, -1),
        ("FIXED_AMOUNT", 1, 1),
        ("FREE_SHIPPING", 0, None),
        ("UNKNOWN", 1, None),
        ("PERCENTAGE", True, None),
        ("FIXED_AMOUNT", 1.5, None),
        ("PERCENTAGE", 1000, 2.5),
    ],
)
def test_invalid_item_discount_rules_fail_before_calculation(kind, value, cap):
    with pytest.raises(ValueError):
        ItemDiscount(kind, value, cap)


@pytest.mark.parametrize("cap", [0, -1, True, 1.5, "100"])
def test_invalid_shipping_discount_cap_is_rejected(cap):
    with pytest.raises(ValueError):
        ShippingDiscount(cap)


@pytest.mark.parametrize(
    "seller,quantity,price",
    [
        (0, 1, 1),
        (-1, 1, 1),
        (True, 1, 1),
        (1, 0, 1),
        (1, -1, 1),
        (1, True, 1),
        (1, 1, -1),
        (1, 1, 1.5),
        (1, 1, True),
        (1, 1, "1"),
    ],
)
def test_invalid_price_line_rejects_negative_or_non_integer_money(seller, quantity, price):
    with pytest.raises(ValueError):
        PricingLine(seller, quantity, price)


@pytest.mark.parametrize("basis", [-1, 1.5, True, "100"])
def test_item_discount_rejects_invalid_basis(basis):
    with pytest.raises(ValueError):
        calculate_item_discount(ItemDiscount("FIXED_AMOUNT", 1), basis)
