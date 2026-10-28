"""Despatch Gmail search efficiency and sender security checks."""
from app.services.tiom_despatch_mail import _gmail_query


def test_filter_query_contains_all_nine_approved_senders():
    from app.routers.tiom_despatch import DEFAULT_SENDERS
    query = _gmail_query({email for email, name in DEFAULT_SENDERS})
    assert "after:2026/10/26" in query
    assert "has:attachment" in query
    assert "-label:NMTPL_DESPATCH_PROCESSED" in query
    assert query.count("from:") == 9
    assert "from:chinmaykumarpanda@gmail.com" in query
    assert "from:dillip.sahu80@gmail.com" in query


def test_empty_and_suspicious_sender_rejected_before_gmail_search():
    assert _gmail_query(set()) == ""
    assert _gmail_query({"abc@example.com } OR from:anyone"}) == ""
