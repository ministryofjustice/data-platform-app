from ai_gateway.templatetags.usage_extras import usd


class TestUSD:
    def test_formatting(self):
        assert usd(value=10) == "$10.00"
        assert usd(value=10.5, max_decimal_places=2) == "$10.50"
        assert usd(value=0.00122, max_decimal_places=2) == "$0.00"
        assert usd(value=0.01010, max_decimal_places=2) == "$0.01"
        assert usd(value=0.00122, max_decimal_places=4) == "$0.0012"
        assert usd(value=0.01010, max_decimal_places=4) == "$0.0101"
        assert usd(value=0.01000, max_decimal_places=4) == "$0.01"
        assert usd(value=None) == "-"
        assert usd(value="invalid") == "-"
