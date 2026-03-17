import uuid

from django.db import models

from projects.models import Project

from .utils import normalize_attribute_value


class LogEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    project = models.ForeignKey(Project, blank=False, null=False, on_delete=models.DO_NOTHING)

    ingested_at = models.DateTimeField(blank=False, null=False)
    digested_at = models.DateTimeField(blank=False, null=False, db_index=True)
    timestamp = models.DateTimeField(blank=False, null=False, db_index=True)

    level = models.CharField(max_length=32, blank=True, null=False, default="")
    body = models.TextField(blank=True, null=False, default="")
    logger_name = models.CharField(max_length=255, blank=True, null=False, default="")
    message_template = models.CharField(max_length=1024, blank=True, null=False, default="")
    trace_id = models.CharField(max_length=36, blank=True, null=False, default="")
    span_id = models.CharField(max_length=32, blank=True, null=False, default="")
    origin = models.CharField(max_length=255, blank=True, null=False, default="")
    sdk_name = models.CharField(max_length=255, blank=True, null=False, default="")
    sdk_version = models.CharField(max_length=255, blank=True, null=False, default="")
    release = models.CharField(max_length=250, blank=True, null=False, default="")
    environment = models.CharField(max_length=64, blank=True, null=False, default="")
    sequence = models.BigIntegerField(blank=False, null=False, default=0)

    project_log_order = models.PositiveIntegerField(blank=False, null=False)

    raw_attributes = models.JSONField(default=dict)

    class Meta:
        unique_together = [
            ("project", "project_log_order"),
        ]
        indexes = [
            models.Index(fields=["project", "timestamp", "ingested_at", "sequence", "id"]),
            models.Index(fields=["project", "digested_at"]),
            models.Index(fields=["digested_at", "project_log_order"]),
            models.Index(fields=["project", "project_log_order"]),
            models.Index(fields=["project", "level"]),
            models.Index(fields=["project", "logger_name"]),
            models.Index(fields=["project", "trace_id"]),
            models.Index(fields=["project", "span_id"]),
            models.Index(fields=["project", "message_template"]),
            models.Index(fields=["project", "origin"]),
            models.Index(fields=["project", "release"]),
            models.Index(fields=["project", "environment"]),
            models.Index(fields=["project", "sdk_name"]),
            models.Index(fields=["project", "sdk_version"]),
        ]

    def __str__(self):
        return f"LogEntry({self.project_id}, {self.timestamp}, {self.level})"

    def get_absolute_url(self):
        return f"/projects/{self.project_id}/logs/{self.id}/"

    @property
    def sequence_display(self):
        if "sentry.timestamp.sequence" in self.raw_attributes:
            raw_sequence = normalize_attribute_value(self.raw_attributes["sentry.timestamp.sequence"])
            try:
                return int(raw_sequence)
            except (TypeError, ValueError):
                pass

        if self.sequence == 0:
            return None

        return self.sequence

    def _display(self, value):
        return normalize_attribute_value(value)

    @property
    def display_level(self):
        return self._display(self.level)

    @property
    def display_logger_name(self):
        return self._display(self.logger_name)

    @property
    def display_message_template(self):
        return self._display(self.message_template)

    @property
    def display_origin(self):
        return self._display(self.origin)

    @property
    def display_sdk_name(self):
        return self._display(self.sdk_name)

    @property
    def display_sdk_version(self):
        return self._display(self.sdk_version)

    @property
    def display_release(self):
        return self._display(self.release)

    @property
    def display_environment(self):
        return self._display(self.environment)

    @property
    def display_raw_attributes(self):
        return {key: normalize_attribute_value(value) for key, value in self.raw_attributes.items()}
