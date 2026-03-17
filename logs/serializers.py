from rest_framework import serializers

from bugsink.api_serializers import UTCModelSerializer

from .models import LogEntry


class LogEntryListSerializer(UTCModelSerializer):
    sequence = serializers.SerializerMethodField()

    class Meta:
        model = LogEntry
        fields = [
            "id",
            "project",
            "ingested_at",
            "digested_at",
            "timestamp",
            "level",
            "body",
            "logger_name",
            "message_template",
            "trace_id",
            "span_id",
            "origin",
            "sdk_name",
            "sdk_version",
            "release",
            "environment",
            "sequence",
        ]

    def get_sequence(self, obj):
        return obj.sequence_display


class LogEntryDetailSerializer(LogEntryListSerializer):
    class Meta(LogEntryListSerializer.Meta):
        fields = LogEntryListSerializer.Meta.fields + [
            "raw_attributes",
            "project_log_order",
        ]
