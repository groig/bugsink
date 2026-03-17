FILTER_ALIASES = {
    "level": "level",
    "logger": "logger_name",
    "logger_name": "logger_name",
    "trace": "trace_id",
    "trace_id": "trace_id",
    "span": "span_id",
    "span_id": "span_id",
    "template": "message_template",
    "message_template": "message_template",
    "origin": "origin",
    "release": "release",
    "environment": "environment",
    "sdk_name": "sdk_name",
    "sdk_version": "sdk_version",
}


def get_log_filter_values(params):
    values = {
        "text": (params.get("text") or params.get("q") or "").strip(),
    }

    for param_name in FILTER_ALIASES:
        values[param_name] = (params.get(param_name) or "").strip()

    return values


def apply_log_filters(queryset, params):
    values = get_log_filter_values(params)

    if values["text"]:
        queryset = queryset.filter(body__icontains=values["text"])

    seen_fields = set()
    for param_name, field_name in FILTER_ALIASES.items():
        value = values[param_name]
        if not value or field_name in seen_fields:
            continue

        queryset = queryset.filter(**{field_name: value})
        seen_fields.add(field_name)

    return queryset
