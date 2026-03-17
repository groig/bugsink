import ast


def normalize_attribute_value(value):
    if isinstance(value, dict) and set(value.keys()) == {"value", "type"}:
        return normalize_attribute_value(value["value"])

    if isinstance(value, list):
        return [normalize_attribute_value(item) for item in value]

    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") and "'value'" in stripped and "'type'" in stripped:
            try:
                parsed = ast.literal_eval(stripped)
            except (ValueError, SyntaxError):
                return value

            if isinstance(parsed, dict):
                return normalize_attribute_value(parsed)

    return value
