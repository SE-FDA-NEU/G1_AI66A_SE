"""US16 / #135: expected prices come from the promotion contract, not the service."""

import pytest

from src.services.pricing import (
    PRICING_POLICY_VERSION,
    SHIPPING_FEE_VND,
    ItemDiscount,
    PricingError,
    PricingLine,
    ShippingDiscount,
    allocate_platform_discount,
    calculate_item_discount,
    price_order,
)


def test_contract_example_totals_433000_and_preserves_funding_breakdown():
    lines = [PricingLine(2, 2, 150_000), PricingLine(3, 1, 200_000)]

    result = price_order(
        lines,
        shop_discounts={2: ItemDiscount("FIXED_AMOUNT", 30_000)},
        platform_discount=ItemDiscount("PERCENTAGE", 1000, max_discount=50_000),
        shipping_discount=ShippingDiscount(max_discount=15_000),
    )

    shop_a, shop_b = result.seller_orders
    assert (shop_a.subtotal, shop_a.shop_discount, shop_a.platform_discount) == (
        300_000,
        30_000,
        27_000,
    )
    assert (shop_b.subtotal, shop_b.shop_discount, shop_b.platform_discount) == (
        200_000,
        0,
        20_000,
    )
    assert (shop_a.shipping_fee, shop_a.shipping_discount, shop_a.total_amount) == (
        20_000,
        15_000,
        248_000,
    )
    assert (shop_b.shipping_fee, shop_b.shipping_discount, shop_b.total_amount) == (
        20_000,
        15_000,
        185_000,
    )
    assert (result.subtotal, result.shop_discount, result.platform_discount) == (
        500_000,
        30_000,
        47_000,
    )
    assert (result.shipping_fee, result.shipping_discount, result.grand_total) == (
        40_000,
        30_000,
        433_000,
    )
    assert result.pricing_policy_version == PRICING_POLICY_VERSION == "US16-V1"
    assert all(row.pricing_policy_version == "US16-V1" for row in result.seller_orders)


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
    "bases,discount,expected",
    [
        ({2: 100, 3: 200}, 100, {2: 33, 3: 67}),
        ({4: 100, 3: 100, 2: 100}, 100, {2: 34, 3: 33, 4: 33}),
        ({2: 0, 3: 1000, 4: 3000}, 999, {2: 0, 3: 250, 4: 749}),
        ({2: 0, 3: 0}, 0, {2: 0, 3: 0}),
        ({2: 1, 3: 2}, 3, {2: 1, 3: 2}),
        ({2: 100, 3: 100}, 0, {2: 0, 3: 0}),
        ({2: 2**60, 3: 2**60 + 1}, 1, {2: 0, 3: 1}),
    ],
)
def test_largest_remainder_allocation_contract_cases(bases, discount, expected):
    assert allocate_platform_discount(discount, bases) == expected


@pytest.mark.parametrize(
    "shop,platform,shipping,expected_total",
    [
        (False, False, False, 340_000),
        (True, False, False, 330_000),
        (False, True, False, 310_000),
        (False, False, True, 310_000),
        (True, True, False, 300_000),
        (True, False, True, 300_000),
        (False, True, True, 280_000),
        (True, True, True, 270_000),
    ],
)
def test_voucher_stacking_decision_table(shop, platform, shipping, expected_total):
    result = price_order(
        [PricingLine(2, 1, 100_000), PricingLine(3, 1, 200_000)],
        shop_discounts={2: ItemDiscount("FIXED_AMOUNT", 10_000)} if shop else None,
        platform_discount=ItemDiscount("FIXED_AMOUNT", 30_000) if platform else None,
        shipping_discount=ShippingDiscount(15_000) if shipping else None,
    )

    assert result.grand_total == expected_total
    assert sum(row.total_amount for row in result.seller_orders) == expected_total
    if shop and platform:
        assert [row.platform_discount for row in result.seller_orders] == [9310, 20_690]


def test_group_lines_and_charge_shipping_once_per_seller():
    result = price_order(
        [
            PricingLine(3, 1, 9),
            PricingLine(2, 2, 100),
            PricingLine(2, 3, 20),
        ]
    )

    assert [(row.seller_id, row.subtotal) for row in result.seller_orders] == [(2, 260), (3, 9)]
    assert result.shipping_fee == 2 * SHIPPING_FEE_VND == 40_000
    assert result.grand_total == 40_269


@pytest.mark.parametrize("cap,expected", [(None, 40_000), (30_000, 40_000), (1, 2)])
def test_free_shipping_cap_is_applied_per_seller_order(cap, expected):
    result = price_order(
        [PricingLine(2, 1, 1), PricingLine(3, 1, 1)],
        shipping_discount=ShippingDiscount(cap),
    )

    assert result.shipping_discount == expected
    assert result.grand_total == 2 + 40_000 - expected


def test_fully_discounted_shop_gets_no_platform_allocation_and_still_has_shipping():
    result = price_order(
        [PricingLine(2, 1, 100), PricingLine(3, 1, 300)],
        shop_discounts={2: ItemDiscount("FIXED_AMOUNT", 1000)},
        platform_discount=ItemDiscount("FIXED_AMOUNT", 999),
    )

    assert [(row.shop_discount, row.platform_discount) for row in result.seller_orders] == [
        (100, 0),
        (0, 300),
    ]
    assert result.grand_total == 40_000


@pytest.mark.parametrize(
    "lines,kwargs",
    [
        ([PricingLine(2, 1, 0)], {"platform_discount": ItemDiscount("FIXED_AMOUNT", 1)}),
        (
            [PricingLine(2, 1, 100)],
            {
                "shop_discounts": {2: ItemDiscount("FIXED_AMOUNT", 100)},
                "platform_discount": ItemDiscount("FIXED_AMOUNT", 1),
            },
        ),
        ([PricingLine(2, 1, 1)], {"platform_discount": ItemDiscount("PERCENTAGE", 1)}),
        ([PricingLine(2, 1, 1)], {"shop_discounts": {2: ItemDiscount("PERCENTAGE", 1)}}),
    ],
)
def test_zero_effect_requested_item_voucher_is_not_applicable(lines, kwargs):
    with pytest.raises(PricingError) as error:
        price_order(lines, **kwargs)

    assert error.value.code == "ERR_VOUCHER_NOT_APPLICABLE"
    assert error.value.status == 409


def test_no_selected_lines_is_an_empty_cart():
    with pytest.raises(PricingError) as error:
        price_order([])

    assert error.value.code == "ERR_EMPTY_CART"
    assert error.value.status == 400


def test_shop_discount_for_an_absent_seller_is_rejected():
    with pytest.raises(ValueError, match="seller"):
        price_order([PricingLine(2, 1, 100)], shop_discounts={3: ItemDiscount("FIXED_AMOUNT", 1)})


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


@pytest.mark.parametrize(
    "discount,bases",
    [
        (-1, {2: 10}),
        (11, {2: 10}),
        (1, {2: 0}),
        (0, {2: -1}),
        (1.5, {2: 10}),
        (True, {2: 10}),
        (1, {2: 1.5}),
        (0, {False: 1}),
    ],
)
def test_invalid_allocation_inputs_are_rejected(discount, bases):
    with pytest.raises(ValueError):
        allocate_platform_discount(discount, bases)


@pytest.mark.parametrize("basis", [-1, 1.5, True, "100"])
def test_item_discount_rejects_invalid_basis(basis):
    with pytest.raises(ValueError):
        calculate_item_discount(ItemDiscount("FIXED_AMOUNT", 1), basis)


def test_free_shipping_can_cover_fees_after_shop_vouchers_cover_all_items():
    result = price_order(
        [PricingLine(2, 1, 100), PricingLine(3, 1, 200)],
        shop_discounts={2: ItemDiscount("FIXED_AMOUNT", 100), 3: ItemDiscount("FIXED_AMOUNT", 200)},
        shipping_discount=ShippingDiscount(),
    )

    assert result.subtotal == result.shop_discount == 300
    assert result.platform_discount == 0
    assert result.shipping_fee == result.shipping_discount == 40_000
    assert result.grand_total == 0
