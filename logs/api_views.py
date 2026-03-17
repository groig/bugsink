from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from bugsink.api_mixins import AtomicRequestMixin
from bugsink.api_pagination import AscDescCursorPagination
from bugsink.utils import assert_

from .filters import apply_log_filters
from .models import LogEntry
from .serializers import LogEntryListSerializer, LogEntryDetailSerializer


class LogPagination(AscDescCursorPagination):
    base_ordering = ("timestamp", "ingested_at", "sequence", "id")
    page_size = 250
    default_direction = "desc"


class LogEntryViewSet(AtomicRequestMixin, viewsets.ReadOnlyModelViewSet):
    queryset = LogEntry.objects.all()
    serializer_class = LogEntryListSerializer
    pagination_class = LogPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="project",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Filter logs by project id (required).",
            ),
            OpenApiParameter(
                name="text",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Plain-text search on the log body.",
            ),
            OpenApiParameter(name="level", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="logger", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="trace", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="span", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="template", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="origin", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="release", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(
                name="environment", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="sdk_name", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(
                name="sdk_version", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(
                name="order",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=["asc", "desc"],
                description="Sort order of timestamp/ingested_at/sequence/id (default: desc).",
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def filter_queryset(self, queryset):
        if self.action != "list":
            return queryset

        project = self.request.query_params.get("project")
        if not project:
            raise ValidationError({"project": ["This field is required."]})

        queryset = queryset.filter(project=project)
        return apply_log_filters(queryset, self.request.query_params)

    def get_object(self):
        queryset = self.get_queryset()

        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        assert_(
            lookup_url_kwarg in self.kwargs,
            'Expected view %s to be called with a URL keyword argument named "%s".'
            % (self.__class__.__name__, lookup_url_kwarg),
        )

        obj = get_object_or_404(queryset, **{self.lookup_field: self.kwargs[lookup_url_kwarg]})
        self.check_object_permissions(self.request, obj)
        return obj

    def get_serializer_class(self):
        return LogEntryDetailSerializer if self.action == "retrieve" else LogEntryListSerializer
