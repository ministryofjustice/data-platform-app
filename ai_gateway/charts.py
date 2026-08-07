"""Dependency-free helpers for turning spend rows into simple SVG bar charts.

Charts are rendered server-side as plain SVG (no JavaScript charting library),
matching this project's existing "no new front-end dependency" approach. Each
chart is offered as a progressive-disclosure alternative to its table, using
the same ``<details>`` pattern as the "Show filter" control on the key
creation page.
"""

from __future__ import annotations

from typing import Any

CHART_WIDTH = 600
CHART_HEIGHT = 220
CHART_PADDING_LEFT = 48
CHART_PADDING_BOTTOM = 28
CHART_PADDING_TOP = 16
BAR_GAP = 8


def bar_chart(rows: list[dict[str, Any]], *, label_key: str, value_key: str) -> dict[str, Any]:
    """Return SVG geometry for a simple bar chart of ``rows``.

    ``rows`` should already be in the order the chart should display (typically
    oldest-to-newest for spend-over-time charts). Returns a dict with the
    overall SVG dimensions, y-axis gridlines, and one bar per row, ready to
    drop straight into an SVG template.
    """
    plot_width = CHART_WIDTH - CHART_PADDING_LEFT
    plot_height = CHART_HEIGHT - CHART_PADDING_TOP - CHART_PADDING_BOTTOM
    values = [row.get(value_key) or 0 for row in rows]
    max_value = max(values) if values else 0
    axis_max = _round_up_for_axis(max_value)

    bar_count = len(rows) or 1
    bar_width = max((plot_width - (BAR_GAP * (bar_count - 1))) / bar_count, 1)

    bars = []
    for index, row in enumerate(rows):
        value = row.get(value_key) or 0
        bar_height = (value / axis_max) * plot_height if axis_max else 0
        x = CHART_PADDING_LEFT + index * (bar_width + BAR_GAP)
        y = CHART_PADDING_TOP + (plot_height - bar_height)
        bars.append(
            {
                "x": round(x, 2),
                "y": round(y, 2),
                "width": round(bar_width, 2),
                "height": round(bar_height, 2),
                "label": row.get(label_key),
                "value": value,
            }
        )

    gridlines = _gridlines(axis_max, plot_height)

    return {
        "width": CHART_WIDTH,
        "height": CHART_HEIGHT,
        "plot_left": CHART_PADDING_LEFT,
        "plot_bottom": CHART_HEIGHT - CHART_PADDING_BOTTOM,
        "bars": bars,
        "gridlines": gridlines,
        "axis_max": axis_max,
    }


def _gridlines(axis_max: float, plot_height: float, count: int = 4) -> list[dict[str, Any]]:
    """Return ``count`` evenly spaced horizontal gridlines with their axis labels."""
    if axis_max <= 0:
        return [{"y": CHART_PADDING_TOP + plot_height, "label": "0"}]

    lines = []
    for step in range(count + 1):
        fraction = step / count
        value = axis_max * fraction
        y = CHART_PADDING_TOP + plot_height * (1 - fraction)
        lines.append({"y": round(y, 2), "label": _format_axis_label(value)})
    return lines


def _format_axis_label(value: float) -> str:
    if value >= 100:
        return f"${value:.0f}"
    return f"${value:.2f}".rstrip("0").rstrip(".")


def _round_up_for_axis(value: float) -> float:
    """Round ``value`` up to a "nice" axis maximum (never zero unless value is zero)."""
    if value <= 0:
        return 0
    magnitude = 1
    while magnitude * 10 <= value:
        magnitude *= 10
    step = magnitude / 5 or 0.01
    steps = -(-value // step)  # ceiling division
    return round(steps * step, 2)
