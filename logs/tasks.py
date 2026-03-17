import json
import logging
import os

from snappea.decorators import shared_task

from ingest.filestore import get_filename_for_event_id

from .ingest import digest_log_payloads


logger = logging.getLogger("bugsink.logs")


@shared_task
def digest_log_entries(log_metadata):
    opened = []

    try:
        payloads = []
        for filetype in log_metadata["filetypes"]:
            filename = get_filename_for_event_id(log_metadata["ingestion_id"], filetype=filetype)
            with open(filename, "rb") as handle:
                payloads.append(json.loads(handle.read().decode("utf-8")))
                opened.append(filename)

        digest_log_payloads(log_metadata, payloads)
    finally:
        errors = []
        for filename in opened:
            try:
                os.unlink(filename)
            except FileNotFoundError as exc:
                errors.append(exc)
        if errors:
            raise Exception(errors)
