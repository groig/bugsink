import json
import logging
from datetime import datetime, timezone

from django.db.models import Sum

from compat.timestamp import parse_timestamp
from bugsink.app_settings import get_settings
from bugsink.transaction import immediate_atomic
from events.retention import eviction_target
from ingest.event_counter import check_for_thresholds
from phonehome.models import Installation
from projects.models import Project

from .models import LogEntry
from .utils import normalize_attribute_value


logger = logging.getLogger("bugsink.logs")


QUOTA_THRESHOLDS = {
    "Installation": [
        ("minute", 5, "MAX_LOGS_PER_5_MINUTES"),
        ("hour", 1, "MAX_LOGS_PER_HOUR"),
        ("month", 1, "MAX_LOGS_PER_MONTH"),
    ],
    "Project": [
        ("minute", 5, "MAX_LOGS_PER_PROJECT_PER_5_MINUTES"),
        ("hour", 1, "MAX_LOGS_PER_PROJECT_PER_HOUR"),
        ("month", 1, "MAX_LOGS_PER_PROJECT_PER_MONTH"),
    ],
}

EMPTY_TRACE_ID = "00000000-0000-0000-0000-000000000000"


def is_log_quota_still_exceeded(obj, now):
    if obj.log_quota_exceeded_until is None or now >= obj.log_quota_exceeded_until:
        return False

    period_name, nr_of_periods, gte_threshold = json.loads(obj.log_quota_exceeded_reason)
    relevant_setting = [
        key for (period, periods, key) in QUOTA_THRESHOLDS[type(obj).__name__]
        if period == period_name and periods == nr_of_periods
    ][0]

    if get_settings()[relevant_setting] > gte_threshold:
        return False

    return True


def count_installation_periods_and_act_on_it(installation, now):
    thresholds = [(period, periods, get_settings()[key]) for (period, periods, key) in QUOTA_THRESHOLDS["Installation"]]
    min_threshold = min(gte_threshold for (_, _, gte_threshold) in thresholds)

    if is_log_quota_still_exceeded(installation, now):
        return False

    digested_log_count = (Project.objects.aggregate(total=Sum("digested_log_count"))["total"] or 0) + 1

    if ((digested_log_count >= installation.next_log_quota_check) or
            (installation.next_log_quota_check - digested_log_count > min_threshold)):

        states = check_for_thresholds(
            LogEntry.objects.all(), now, thresholds, 1, order_field="project_log_order")

        until, threshold_info = max(
            [(below_from, threshold_info) for (is_exceeded, below_from, _, threshold_info) in states if is_exceeded],
            default=(None, None),
        )
        check_again_after = max(1, min([check_after for (_, _, check_after, _) in states], default=1))

        installation.log_quota_exceeded_until = until
        installation.log_quota_exceeded_reason = json.dumps(threshold_info)
        installation.next_log_quota_check = digested_log_count + check_again_after
        installation.save(update_fields=[
            "log_quota_exceeded_until",
            "log_quota_exceeded_reason",
            "next_log_quota_check",
        ])

    return True


def count_project_periods_and_act_on_it(project, now):
    thresholds = [(period, periods, get_settings()[key]) for (period, periods, key) in QUOTA_THRESHOLDS["Project"]]
    min_threshold = min(gte_threshold for (_, _, gte_threshold) in thresholds)

    if is_log_quota_still_exceeded(project, now):
        return False

    project.digested_log_count += 1

    if ((project.digested_log_count >= project.next_log_quota_check) or
            (project.next_log_quota_check - project.digested_log_count > min_threshold)):

        states = check_for_thresholds(
            LogEntry.objects.filter(project=project), now, thresholds, 1, order_field="project_log_order")

        until, threshold_info = max(
            [(below_from, threshold_info) for (is_exceeded, below_from, _, threshold_info) in states if is_exceeded],
            default=(None, None),
        )
        check_again_after = min([check_after for (_, _, check_after, _) in states], default=1)

        project.log_quota_exceeded_until = until
        project.log_quota_exceeded_reason = json.dumps(threshold_info)
        project.next_log_quota_check = project.digested_log_count + check_again_after
        project.save(update_fields=[
            "digested_log_count",
            "log_quota_exceeded_until",
            "log_quota_exceeded_reason",
            "next_log_quota_check",
        ])
        return True

    project.save(update_fields=["digested_log_count"])
    return True


def should_evict(project, stored_log_count):
    return stored_log_count > project.get_retention_max_log_count()


def evict_for_max_logs(project, stored_log_count):
    target = eviction_target(project.get_retention_max_log_count(), stored_log_count)

    to_delete = list(
        LogEntry.objects.filter(project=project)
        .order_by("timestamp", "ingested_at", "sequence", "id")
        .values_list("id", flat=True)[:target]
    )
    if not to_delete:
        return 0

    deleted, _ = LogEntry.objects.filter(id__in=to_delete).delete()
    return deleted


def _as_string(value, max_length=None):
    if value in [None, ""]:
        return ""

    value = str(value)
    if max_length is not None:
        return value[:max_length]
    return value


def _as_sequence(value):
    if value in [None, ""]:
        return 0

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_log_payload(payload, ingested_at):
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise ValueError("log payload must contain an items list")

    parsed = []
    for item in items:
        if not isinstance(item, dict):
            logger.warning("skipping malformed log item: expected object, got %r", type(item).__name__)
            continue

        attributes = item.get("attributes", {})
        if not isinstance(attributes, dict):
            logger.warning("skipping malformed log item attributes: expected object, got %r", type(attributes).__name__)
            continue
        attributes = {key: normalize_attribute_value(value) for key, value in attributes.items()}

        timestamp = parse_timestamp(item.get("timestamp"))
        if timestamp is None:
            timestamp = ingested_at

        trace_id = _as_string(item.get("trace_id"), 36)
        if trace_id == EMPTY_TRACE_ID:
            trace_id = ""

        parsed.append({
            "timestamp": timestamp,
            "level": _as_string(item.get("level"), 32),
            "body": _as_string(item.get("body")),
            "logger_name": _as_string(attributes.get("logger.name"), 255),
            "message_template": _as_string(attributes.get("sentry.message.template"), 1024),
            "trace_id": trace_id,
            "span_id": _as_string(item.get("span_id"), 32),
            "origin": _as_string(attributes.get("sentry.origin"), 255),
            "sdk_name": _as_string(attributes.get("sentry.sdk.name"), 255),
            "sdk_version": _as_string(attributes.get("sentry.sdk.version"), 255),
            "release": _as_string(attributes.get("sentry.release"), 250),
            "environment": _as_string(attributes.get("sentry.environment"), 64),
            "sequence": _as_sequence(attributes.get("sentry.timestamp.sequence")),
            "raw_attributes": attributes,
        })

    return parsed


@immediate_atomic()
def digest_log_payloads(log_metadata, payloads, digested_at=None):
    ingested_at = parse_timestamp(log_metadata["ingested_at"])
    digested_at = datetime.now(timezone.utc) if digested_at is None else digested_at

    try:
        project = Project.objects.get(pk=log_metadata["project_id"], is_deleted=False)
    except Project.DoesNotExist:
        return

    installation = Installation.objects.get()

    for payload in payloads:
        try:
            parsed_logs = parse_log_payload(payload, ingested_at)
        except ValueError as exc:
            logger.warning("skipping malformed log payload", exc_info=exc)
            continue

        for parsed_log in parsed_logs:
            if (not count_installation_periods_and_act_on_it(installation, digested_at)
                    or not count_project_periods_and_act_on_it(project, digested_at)):
                return

            project_stored_log_count = project.stored_log_count + 1
            evicted = evict_for_max_logs(project, project_stored_log_count) if should_evict(
                project, project_stored_log_count) else 0

            project.stored_log_count = project_stored_log_count - evicted
            project.save(update_fields=["stored_log_count"])

            LogEntry.objects.create(
                project=project,
                ingested_at=ingested_at,
                digested_at=digested_at,
                project_log_order=project.digested_log_count,
                **parsed_log,
            )
