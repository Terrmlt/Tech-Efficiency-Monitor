from django import template

register = template.Library()

PALETTE = [
    '#0d6efd', '#198754', '#fd7e14', '#6f42c1',
    '#dc3545', '#0dcaf0', '#ffc107', '#20c997',
]

@register.filter
def section_color(counter):
    idx = (int(counter) - 1) % len(PALETTE)
    return PALETTE[idx]
