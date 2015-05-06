from django.utils import six

def to_boolean(value):
    """Convert string to Python boolean object.

    Arguments:
    - `string`:
    """
    if isinstance(value, six.string_types) and value.lower() in ('false', '0'):
        value = False
    else:
        value = bool(value)

    return value
