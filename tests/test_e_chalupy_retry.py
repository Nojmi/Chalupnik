import pytest
import requests

from scraper.profiles import e_chalupy


class _Resp:
    def __init__(self, code=200):
        self.status_code = code


def test_get_retries_then_succeeds(monkeypatch):
    calls = []

    def fake_get(url, **kw):
        calls.append(1)
        if len(calls) < 3:
            raise requests.ConnectionError("Connection aborted.")
        return _Resp()

    monkeypatch.setattr(e_chalupy.requests, "get", fake_get)
    monkeypatch.setattr(e_chalupy.time, "sleep", lambda s: None)
    assert e_chalupy._get("http://x").status_code == 200
    assert len(calls) == 3


def test_get_gives_up_after_all_tries(monkeypatch):
    monkeypatch.setattr(e_chalupy.requests, "get", lambda url, **kw: _Resp(503))
    monkeypatch.setattr(e_chalupy.time, "sleep", lambda s: None)
    with pytest.raises(requests.HTTPError):
        e_chalupy._get("http://x", tries=3)
