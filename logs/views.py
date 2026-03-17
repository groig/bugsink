from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from bugsink.decorators import atomic_for_request_method, project_membership_required

from .filters import apply_log_filters, get_log_filter_values
from .models import LogEntry


@atomic_for_request_method
@project_membership_required
def log_list(request, project):
    filters = get_log_filter_values(request.GET)
    log_qs = apply_log_filters(LogEntry.objects.filter(project=project), request.GET).order_by(
        "-timestamp", "-ingested_at", "-sequence", "-id")

    paginator = Paginator(log_qs, 100)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    return render(request, "logs/log_list.html", {
        "page_obj": page_obj,
        "project": project,
        "filters": filters,
        "has_advanced_filters": any(filters[name] for name in [
            "logger", "trace", "span", "template", "origin", "release", "environment", "sdk_name", "sdk_version",
        ]),
    })


@atomic_for_request_method
@project_membership_required
def log_detail(request, project, log_entry_pk):
    log_entry = get_object_or_404(LogEntry, pk=log_entry_pk, project=project)

    return render(request, "logs/log_detail.html", {
        "log_entry": log_entry,
        "project": project,
    })
