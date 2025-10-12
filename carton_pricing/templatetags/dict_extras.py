from django import template
register = template.Library()

@register.filter
def dict_get(d, key):
    try:
        return (d or {}).get(str(key)) or (d or {}).get(int(key))
    except Exception:
        return None
