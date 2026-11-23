"""Regression: later pages of approved-sender WB Gmail must be scanned."""
import unittest
from unittest.mock import patch

from scripts import wb_gmail_worker as worker


class _Execute:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self.data


class _Messages:
    def __init__(self):
        self.calls = []
        self.fetched = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        if not kwargs.get("pageToken"):
            return _Execute({
                "messages": [{"id": f"noise-{i}"} for i in range(25)],
                "nextPageToken": "page-two",
            })
        return _Execute({"messages": [{"id": "wb-report"}]})

    def get(self, **kwargs):
        self.fetched.append(kwargs["id"])
        return _Execute({"id": kwargs["id"]})


class _Service:
    def __init__(self):
        self.handler = _Messages()

    def users(self):
        return self

    def messages(self):
        return self.handler


class WbGmailPaginationTests(unittest.TestCase):
    def test_older_wb_mail_is_not_starved_by_first_page(self):
        service = _Service()
        cfg = {
            "gmail_query": "has:attachment filename:xlsx",
            "allowed_senders": ["wb@example.com"],
            "processed_label": "WB_PROCESSED",
            "duplicate_label": "WB_DUPLICATE",
            "error_label": "WB_ERROR",
            "review_required_label": "WB_REVIEW",
            "max_messages_per_poll": 25,
            "max_pages_per_poll": 2,
        }
        with patch.object(worker, "process_message", side_effect=lambda *_: {"status": "DONE"}) as call:
            records = worker.poll_once(service, cfg, {})
        self.assertEqual(len(service.handler.calls), 2)
        self.assertEqual(len(records), 26)
        self.assertEqual(call.call_count, 26)
        self.assertIn("wb-report", service.handler.fetched)
        self.assertEqual(service.handler.calls[1]["pageToken"], "page-two")


if __name__ == "__main__":
    unittest.main()
