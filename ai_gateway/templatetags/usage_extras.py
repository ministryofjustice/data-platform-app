from django import template

register = template.Library()


@register.filter
def usd(value: float | int | None, decimal_places: int = 2) -> str:
    """Format ``value`` as a dollar amount with thousands separators, e.g. ``$9,999.00``."""
    if value is None:
        return "-"

    try:
        decimal_places = int(decimal_places)
        formatted = f"${float(value):,.{decimal_places}f}"
    except TypeError, ValueError:
        return "-"

    if decimal_places == 0:
        return formatted

    whole, decimal = formatted.split(".")
    decimal = decimal.rstrip("0")
    decimal = decimal.ljust(2, "0")
    return f"{whole}.{decimal}"
