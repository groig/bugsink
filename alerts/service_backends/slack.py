import json
from urllib.parse import urlparse

import requests
from django import forms
from django.template.defaultfilters import truncatechars
from django.utils import timezone

from snappea.decorators import shared_task
from bugsink.app_settings import get_settings
from bugsink.transaction import immediate_atomic

from issues.models import Issue


def _get_request_location(parsed_data):
    request = parsed_data.get("request") or {}
    url = request.get("url") or ""
    if not url:
        return ""

    parsed = urlparse(url)
    if parsed.path or parsed.query or parsed.fragment:
        result = parsed.path or "/"
        if parsed.query:
            result += "?" + parsed.query
        if parsed.fragment:
            result += "#" + parsed.fragment
        return result

    return url


def _get_code_location(issue):
    if issue.transaction:
        return issue.transaction

    module_or_file = issue.last_frame_module or issue.last_frame_filename
    if module_or_file and issue.last_frame_function:
        return f"{module_or_file}.{issue.last_frame_function}"
    if issue.last_frame_function:
        return issue.last_frame_function
    return module_or_file


def _get_issue_location(issue):
    event = issue.event_set.order_by("-digest_order").first()
    if event is not None:
        parsed_data = event.get_parsed_data()
        request_location = _get_request_location(parsed_data)
        if request_location:
            return request_location

        transaction = parsed_data.get("transaction") or ""
        if transaction:
            return transaction

    return _get_code_location(issue)


def _get_issue_message(issue):
    return issue.calculated_value or issue.title()


def _build_slack_alert_blocks(issue, state_description, unmute_reason=None):
    blocks = [{
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f":red_circle: *<{get_settings().BASE_URL + issue.get_absolute_url()}|"
                    f"{_safe_markdown(issue.calculated_type or issue.title())}>*",
        },
    }]

    issue_location = _get_issue_location(issue)
    if issue_location:
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": _safe_markdown(issue_location),
            }],
        })

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"```{_safe_markdown(_get_issue_message(issue))}```",
        },
    })
    blocks.append({
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": f"*State:* {_safe_markdown(state_description)}",
        }],
    })

    if unmute_reason:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": _safe_markdown(unmute_reason),
            },
        })

    return blocks


class SlackConfigForm(forms.Form):
    webhook_url = forms.URLField(required=True)

    # Slack does not support multi-channel webhooks, as per the docs:
    # > You cannot override the default channel (chosen by the user who installed your app), username, or icon when
    # > you're using incoming webhooks to post messages. Instead, these values will always inherit from the associated
    # > Slack app configuration.

    def __init__(self, *args, **kwargs):
        config = kwargs.pop("config", None)

        super().__init__(*args, **kwargs)
        if config:
            self.fields["webhook_url"].initial = config.get("webhook_url", "")

    def get_config(self):
        return {
            "webhook_url": self.cleaned_data.get("webhook_url"),
        }


def _safe_markdown(text):
    # Slack assigns a special meaning to some characters, so we need to escape them
    # to prevent them from being interpreted as formatting/special characters.
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("*", "\\*").replace("_", "\\_").replace("`", "\\`"))


def _store_failure_info(service_config_id, exception, response=None):
    """Store failure information in the MessagingServiceConfig with immediate_atomic"""
    from alerts.models import MessagingServiceConfig

    with immediate_atomic(only_if_needed=True):
        try:
            config = MessagingServiceConfig.objects.get(id=service_config_id)

            config.last_failure_timestamp = timezone.now()
            config.last_failure_error_type = type(exception).__name__
            config.last_failure_error_message = str(exception)

            # Handle requests-specific errors
            if response is not None:
                config.last_failure_status_code = response.status_code
                config.last_failure_response_text = response.text[:2000]  # Limit response text size

                # Check if response is JSON
                try:
                    json.loads(response.text)
                    config.last_failure_is_json = True
                except (json.JSONDecodeError, ValueError):
                    config.last_failure_is_json = False
            else:
                # Non-HTTP errors
                config.last_failure_status_code = None
                config.last_failure_response_text = None
                config.last_failure_is_json = None

            config.save()
        except MessagingServiceConfig.DoesNotExist:
            # Config was deleted while task was running
            pass


def _store_success_info(service_config_id):
    """Clear failure information on successful operation"""
    from alerts.models import MessagingServiceConfig

    with immediate_atomic(only_if_needed=True):
        try:
            config = MessagingServiceConfig.objects.get(id=service_config_id)
            config.clear_failure_status()
            config.save()
        except MessagingServiceConfig.DoesNotExist:
            # Config was deleted while task was running
            pass


@shared_task
def slack_backend_send_test_message(webhook_url, project_name, display_name, service_config_id):
    # See Slack's Block Kit Builder

    data = {"text": "Test message by Bugsink to test the webhook setup.",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "TEST issue",
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Test message by Bugsink to test the webhook setup.",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": "*project*: " + _safe_markdown(project_name),
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*message backend*: " + _safe_markdown(display_name),
                        },
                    ]
                }
            ]}

    try:
        result = requests.post(
            webhook_url,
            data=json.dumps(data),
            headers={"Content-Type": "application/json"},
            timeout=5,
        )

        result.raise_for_status()

        _store_success_info(service_config_id)
    except requests.RequestException as e:
        response = getattr(e, 'response', None)
        _store_failure_info(service_config_id, e, response)

    except Exception as e:
        _store_failure_info(service_config_id, e)


@shared_task
def slack_backend_send_alert(
        webhook_url, issue_id, state_description, alert_article, alert_reason, service_config_id, unmute_reason=None):

    issue = Issue.objects.get(id=issue_id)
    title = truncatechars(issue.title().replace("|", ""), 150)

    data = {
        "text": title,
        "blocks": _build_slack_alert_blocks(issue, state_description, unmute_reason),
    }

    try:
        result = requests.post(
            webhook_url,
            data=json.dumps(data),
            headers={"Content-Type": "application/json"},
            timeout=5,
        )

        result.raise_for_status()

        _store_success_info(service_config_id)
    except requests.RequestException as e:
        response = getattr(e, 'response', None)
        _store_failure_info(service_config_id, e, response)

    except Exception as e:
        _store_failure_info(service_config_id, e)


class SlackBackend:
    def __init__(self, service_config):
        self.service_config = service_config

    @classmethod
    def get_form_class(cls):
        return SlackConfigForm

    def send_test_message(self):
        config = json.loads(self.service_config.config)
        slack_backend_send_test_message.delay(
            config["webhook_url"],
            self.service_config.project.name,
            self.service_config.display_name,
            self.service_config.id,
        )

    def send_alert(self, issue_id, state_description, alert_article, alert_reason, **kwargs):
        config = json.loads(self.service_config.config)
        slack_backend_send_alert.delay(
            config["webhook_url"],
            issue_id,
            state_description,
            alert_article,
            alert_reason,
            self.service_config.id,
            **kwargs,
        )
