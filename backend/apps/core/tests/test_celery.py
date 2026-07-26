import json
import logging

import pytest
from celery import current_app
from django.conf import settings

from apps.core.tasks import log_worker_probe
from config import celery_app


def test_celery_application_imports_and_discovers_diagnostic_task():
    celery_app.loader.import_default_modules()

    assert celery_app.main == "ludora"
    assert log_worker_probe.name in celery_app.tasks


def test_celery_configuration_uses_django_settings():
    assert celery_app.conf.broker_url == settings.CELERY_BROKER_URL
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.timezone == settings.TIME_ZONE
    assert celery_app.conf.task_ignore_result is True
    assert celery_app.conf.task_always_eager is True
    assert celery_app.conf.task_eager_propagates is True


def test_diagnostic_task_executes_eagerly_without_contacting_broker(caplog):
    with caplog.at_level(logging.INFO, logger="apps.core.tasks"):
        result = log_worker_probe.delay("pytest-worker-probe")

    assert result.get() == {
        "message": "pytest-worker-probe",
        "status": "processed",
    }
    assert result.id
    assert current_app.conf.task_always_eager is True
    record = next(
        record
        for record in caplog.records
        if record.message.startswith("Celery diagnostic task executed")
    )
    assert record.diagnostic_message == "pytest-worker-probe"


def test_diagnostic_task_input_and_output_are_json_serializable():
    payload = {"message": "json-worker-probe"}
    json.dumps(payload)

    result = log_worker_probe.apply(kwargs=payload).get()

    assert json.loads(json.dumps(result)) == {
        "message": "json-worker-probe",
        "status": "processed",
    }


@pytest.mark.parametrize("message", ["", "x" * 201])
def test_diagnostic_task_rejects_invalid_message_length(message):
    with pytest.raises(ValueError, match="between 1 and 200"):
        log_worker_probe.apply(args=[message]).get()
