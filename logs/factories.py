from django.utils import timezone

from projects.models import Project

from .models import LogEntry


def create_log_entry(project=None, timestamp=None, sequence=0, **kwargs):
    if project is None:
        project = Project.objects.create(name="Logs Project")

    if timestamp is None:
        timestamp = timezone.now()

    project.digested_log_count += 1
    project.stored_log_count += 1
    project.save(update_fields=["digested_log_count", "stored_log_count"])

    return LogEntry.objects.create(
        project=project,
        ingested_at=timestamp,
        digested_at=timestamp,
        timestamp=timestamp,
        sequence=sequence,
        project_log_order=project.digested_log_count,
        **kwargs,
    )
