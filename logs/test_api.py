from bugsink.test_utils import TransactionTestCase25251 as TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APIClient

from bsmain.models import AuthToken
from projects.models import Project

from logs.api_views import LogEntryViewSet
from logs.factories import create_log_entry


class LogApiTests(TransactionTestCase):
    def setUp(self):
        self.client = APIClient()
        token = AuthToken.objects.create()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.token}")

        self.project = Project.objects.create(name="Test Project")
        base = timezone.now().replace(microsecond=0)

        self.oldest = create_log_entry(
            project=self.project,
            timestamp=base,
            sequence=1,
            level="info",
            body="oldest body",
            logger_name="app.old",
            raw_attributes={"logger.name": "app.old"},
        )
        self.middle = create_log_entry(
            project=self.project,
            timestamp=base + timezone.timedelta(seconds=1),
            sequence=1,
            level="warning",
            body="middle body",
            logger_name="app.middle",
            trace_id="trace-1",
            message_template="middle %s",
            raw_attributes={
                "logger.name": "app.middle",
                "sentry.message.template": "middle %s",
                "sentry.timestamp.sequence": 1,
            },
        )
        self.latest = create_log_entry(
            project=self.project,
            timestamp=base + timezone.timedelta(seconds=1),
            sequence=2,
            level="error",
            body="latest needle",
            logger_name="app.latest",
            trace_id="trace-2",
            raw_attributes={
                "logger.name": "app.latest",
                "sentry.timestamp.sequence": 2,
            },
        )

    def test_list_requires_project(self):
        response = self.client.get(reverse("api:logentry-list"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual({"project": ["This field is required."]}, response.json())

    def test_detail_by_id(self):
        response = self.client.get(reverse("api:logentry-detail", args=[self.latest.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(self.latest.id))
        self.assertIn("raw_attributes", response.json())

    def test_list_default_desc_order(self):
        response = self.client.get(reverse("api:logentry-list"), {"project": str(self.project.id)})
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.json()["results"]]
        self.assertEqual(ids, [str(self.latest.id), str(self.middle.id), str(self.oldest.id)])

    def test_list_filters(self):
        response = self.client.get(reverse("api:logentry-list"), {
            "project": str(self.project.id),
            "text": "needle",
            "level": "error",
            "logger": "app.latest",
            "trace": "trace-2",
        })
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.json()["results"]]
        self.assertEqual(ids, [str(self.latest.id)])

    def test_list_filter_by_template_alias(self):
        response = self.client.get(reverse("api:logentry-list"), {
            "project": str(self.project.id),
            "template": "middle %s",
        })
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.json()["results"]]
        self.assertEqual(ids, [str(self.middle.id)])


class LogPaginationTests(TransactionTestCase):
    def setUp(self):
        self.client = APIClient()
        token = AuthToken.objects.create()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.token}")

        self.old_size = LogEntryViewSet.pagination_class.page_size
        LogEntryViewSet.pagination_class.page_size = 2

        self.project = Project.objects.create(name="Pagination Project")
        base = timezone.now().replace(microsecond=0)
        self.logs = [
            create_log_entry(project=self.project, timestamp=base, sequence=1, body="log 1"),
            create_log_entry(
                project=self.project,
                timestamp=base + timezone.timedelta(seconds=1),
                sequence=1,
                body="log 2",
            ),
            create_log_entry(
                project=self.project,
                timestamp=base + timezone.timedelta(seconds=2),
                sequence=1,
                body="log 3",
            ),
        ]

    def tearDown(self):
        LogEntryViewSet.pagination_class.page_size = self.old_size

    def _ids(self, response):
        return [row["id"] for row in response.json()["results"]]

    def test_desc_pagination(self):
        response = self.client.get(reverse("api:logentry-list"), {"project": str(self.project.id)})
        self.assertEqual(self._ids(response), [str(self.logs[2].id), str(self.logs[1].id)])

        response = self.client.get(response.json()["next"])
        self.assertEqual(self._ids(response), [str(self.logs[0].id)])
