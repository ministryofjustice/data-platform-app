from django import template

register = template.Library()


@register.filter
def usd(value: float | int | None) -> str:
    """Format ``value`` as a dollar amount with thousands separators, e.g. ``$9,999.00``."""
    if value is None:
        return "-"
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "-"
