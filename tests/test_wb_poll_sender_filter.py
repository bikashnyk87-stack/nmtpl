"""Regression tests for WB Gmail source filtering and the bounded poll."""
from unittest.mock import MagicMock, patch

import pytest

from scripts.wb_gmail_worker import poll_once


def _cfg(senders):
    return {
        "gmail_query": "has:attachment filename:xlsx",
        "max_messages_per_poll": 25,
        "allowed_senders": senders,
        "processed_label": "NMTPL_WB_PROCESSED",
        "duplicate_label": "NMTPL_WB_DUPLICATE",
        "error_label": "NMTPL_WB_ERROR",
        "review_required_label": "NMTPL_WB_REVIEW_REQUIRED",
    }


def test_poll_filters_approved_senders_before_gmail_limit():
    service = MagicMock()
    service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "wb1"}]
    }
    service.users.return_value.messages.return_value.get.return_value.execute.return_value = {"id": "wb1"}
    with patch("scripts.wb_gmail_worker.process_message", return_value={"status": "DONE"}) as process:
        result = poll_once(service, _cfg(["@amns.in"]), {})

    kwargs = service.users.return_value.messages.return_value.list.call_args.kwargs
    assert kwargs["maxResults"] == 25
    assert "from:@amns.in" in kwargs["q"]
    assert "-label:NMTPL_WB_PROCESSED" in kwargs["q"]
    assert "has:attachment filename:xlsx" in kwargs["q"]
    process.assert_called_once()
    assert result == [{"status": "DONE"}]


def test_broad_gmail_domain_match_does_not_replay_unapproved_subdomain():
    from scripts.wb_gmail_worker import process_message, sender_allowed
    assert sender_allowed("feed@amns.in", ["@amns.in"])
    assert not sender_allowed("deepak.jena@ext.amns.in", ["@amns.in"])
    service=MagicMock()
    message={"id":"subdomain1","payload":{"headers":[
        {"name":"From","value":"deepak.jena@ext.amns.in"},
        {"name":"Subject","value":"Other spreadsheet"},
    ]}}
    cfg=_cfg(["@amns.in"])
    cfg["skipped_label"]="NMTPL_WB_SKIPPED"
    with patch("scripts.wb_gmail_worker.apply_labels") as apply:
        result=process_message(service,message,cfg,{"NMTPL_WB_SKIPPED":"Label_skip"})
    assert result["status"]=="SKIPPED_SENDER"
    apply.assert_called_once_with(service,"subdomain1",["Label_skip"],[])
    service.users.assert_not_called()


def test_poll_excludes_already_labeled_skipped_sender_messages():
    service=MagicMock()
    service.users.return_value.messages.return_value.list.return_value.execute.return_value={"messages":[]}
    poll_once(service,_cfg(["@amns.in"]),{})
    query=service.users.return_value.messages.return_value.list.call_args.kwargs["q"]
    assert "-label:NMTPL_WB_SKIPPED" in query


def test_poll_rejects_missing_approved_sender_configuration():
    service = MagicMock()
    with pytest.raises(RuntimeError, match="approved senders"):
        poll_once(service, _cfg([]), {})
    service.users.assert_not_called()
