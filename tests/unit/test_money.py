from __future__ import annotations

from decimal import Decimal

from pms.utils.money import monetary_string


def test_monetary_string_normalizes_plain_decimal_transport() -> None:
    assert monetary_string(Decimal("0.012500")) == "0.0125"
    assert monetary_string(Decimal("10.0000")) == "10"
    assert monetary_string(Decimal(0)) == "0"


def test_monetary_string_avoids_float_artifacts() -> None:
    assert monetary_string(0.05) == "0.05"
    assert monetary_string("12.3400") == "12.34"
    assert monetary_string(None) is None
