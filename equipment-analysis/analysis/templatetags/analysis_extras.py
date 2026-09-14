from django import template
from decimal import Decimal, InvalidOperation

register = template.Library()

PALETTE = [
    '#0d6efd', '#198754', '#fd7e14', '#6f42c1',
    '#dc3545', '#0dcaf0', '#ffc107', '#20c997',
]

@register.filter
def section_color(counter):
    idx = (int(counter) - 1) % len(PALETTE)
    return PALETTE[idx]


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def ru_number(value):
    """Format a display-only number using spaces and a decimal comma."""
    if value is None or isinstance(value, bool):
        return '' if value is None else value
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value
    if not number.is_finite():
        return value

    text = format(number, 'f')
    sign = ''
    if text.startswith('-'):
        sign, text = '-', text[1:]
    integer, separator, fraction = text.partition('.')
    grouped = f'{int(integer or "0"):,}'.replace(',', ' ')
    return f'{sign}{grouped}{"," + fraction if separator else ""}'
