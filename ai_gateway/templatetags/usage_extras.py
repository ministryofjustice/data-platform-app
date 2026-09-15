from django import template

register = template.Library()


@register.filter
def usd(value: float | int | None, max_decimal_places: int = 2) -> str:
    """Format ``value`` as a dollar amount with thousands separators, e.g. ``$9,999.00``."""
    if value is None:
        return "-"
    try:
        max_decimal_places = int(max_decimal_places)
        formatted = f"${float(value):,.{max_decimal_places}f}"
    except TypeError, ValueError:
        return "-"

    whole, decimal = formatted.split(".")
    decimal = decimal.rstrip("0")
    decimal = decimal.ljust(2, "0")
    return f"{whole}.{decimal}"
