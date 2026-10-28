"""Local Gmail setup works without Render env vars and never exposes OAuth tokens on LAN."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.routers import automation, tiom_despatch
from scripts.install_pc_gmail_config_safe import patch, AUTOMATION, DESPATCH, JS, INDEX


def test_pc_existing_oauth_file_is_accepted(monkeypatch, tmp_path):
    monkeypatch.setattr(automation, "ROOT", tmp_path)
    monkeypatch.setattr(automation, "RENDER_SECRETS", tmp_path / "no_render_secrets")
    monkeypatch.delenv("GMAIL_TOKEN_JSON", raising=False)
    token = {
        "refresh_token": "fake-private-unit-test-only",
        "client_id": "test-client",
        "client_secret": "test-secret",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    path = tmp_path / "config" / "gmail_token.json"
    path.parent.mkdir()
    path.write_text(json.dumps(token), encoding="utf-8")
    assert json.loads(automation._gmail_token_raw()) == token
    assert automation._prepare_gmail_token() == path


def test_render_token_precedence_over_pc_file(monkeypatch, tmp_path):
    monkeypatch.setattr(automation, "ROOT", tmp_path)
    monkeypatch.setattr(automation, "RENDER_SECRETS", tmp_path / "not_present")
    path = tmp_path / "config" / "gmail_token.json"
    path.parent.mkdir()
    path.write_text('{"refresh_token":"local"}', encoding="utf-8")
    monkeypatch.setenv("GMAIL_TOKEN_JSON", '{"refresh_token":"cloud"}')
    assert json.loads(automation._gmail_token_raw()) == {"refresh_token": "cloud"}


def test_mail_setup_rejected_on_lan_and_render():
    admin = SimpleNamespace(admin=True)
    normal = SimpleNamespace(admin=False)
    def req(ip, host):
        return SimpleNamespace(client=SimpleNamespace(host=ip),headers={"host":host})
    assert tiom_despatch._local_gmail_setup_allowed(req("127.0.0.1","127.0.0.1:8765"),admin)
    assert not tiom_despatch._local_gmail_setup_allowed(req("192.168.1.23","192.168.1.10:8765"),admin)
    assert not tiom_despatch._local_gmail_setup_allowed(req("127.0.0.1","nmtpl-tiom-test.onrender.com"),admin)
    assert not tiom_despatch._local_gmail_setup_allowed(req("127.0.0.1","127.0.0.1:8765"),normal)


def test_pc_installer_surgical_patch_and_cache_bust():
    root = Path(__file__).resolve().parents[1]
    paths = (AUTOMATION,DESPATCH,JS,INDEX)
    current = {n:(root/n).read_text(encoding="utf-8") for n in paths}
    latest = {n:current[n] for n in paths if n!=INDEX}
    result=patch(current,latest)
    assert set(result)==set(paths)
    assert result[AUTOMATION] == current[AUTOMATION]
    assert result[DESPATCH] == current[DESPATCH]
    assert result[JS] == current[JS]
    assert "pc-gmail-config-v2" in result[INDEX]
    assert result[INDEX] != current[INDEX]


def test_gmail_ui_does_not_render_tokens():
    s=(Path(__file__).resolve().parents[1]/JS).read_text(encoding="utf-8")
    assert "gmailTokenConfigured" in s
    assert "localSetupAvailable" in s
    assert "tiomDDGmailConnect" in s
    assert "gmail-connect-local" in s
    assert "password" not in s.lower()
