from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from bugsink.test_utils import TransactionTestCase25251 as TransactionTestCase
from projects.models import Project, ProjectMembership

from .factories import create_log_entry


User = get_user_model()


class LogViewsTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="logs-user", password="test")
        self.project = Project.objects.create(name="Logs Project")
        ProjectMembership.objects.create(project=self.project, user=self.user, accepted=True)
        self.client.force_login(self.user)

        now = timezone.now()
        self.log_entry = create_log_entry(
            project=self.project,
            timestamp=now,
            body="needle body",
            level="error",
            logger_name="app.logger",
            raw_attributes={"logger.name": "app.logger", "foo": "bar"},
        )

    def test_list_page(self):
        response = self.client.get(reverse("log_list", kwargs={"project_pk": self.project.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "needle body")

    def test_list_filters(self):
        response = self.client.get(reverse("log_list", kwargs={"project_pk": self.project.id}), {
            "text": "needle",
            "logger": "app.logger",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "needle body")

    def test_detail_page(self):
        response = self.client.get(reverse("log_detail", kwargs={
            "project_pk": self.project.id,
            "log_entry_pk": self.log_entry.id,
        }))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "foo")
        self.assertContains(response, "bar")

    def test_legacy_typed_attributes_render_cleanly(self):
        legacy_log_entry = create_log_entry(
            project=self.project,
            body="legacy body",
            logger_name="{'value': 'legacy.logger', 'type': 'string'}",
            origin="{'value': 'auto.log.stdlib', 'type': 'string'}",
            raw_attributes={
                "logger.name": {"value": "legacy.logger", "type": "string"},
                "sentry.timestamp.sequence": {"value": 9, "type": "integer"},
            },
        )

        response = self.client.get(reverse("log_list", kwargs={"project_pk": self.project.id}))
        self.assertContains(response, "legacy.logger")
        self.assertNotContains(response, "{&#x27;value&#x27;:")

        response = self.client.get(reverse("log_detail", kwargs={
            "project_pk": self.project.id,
            "log_entry_pk": legacy_log_entry.id,
        }))
        self.assertContains(response, "legacy.logger")
        self.assertContains(response, ">9<")
