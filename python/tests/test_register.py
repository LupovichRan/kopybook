"""`kopybook register`: credentials never come from or leak through the --registry URL."""
import base64
import io
import os
import socket
import subprocess
import sys
import traceback
import urllib.error

import pytest

from kopybook import cli
from conftest import CORPUS, HERE

CB = os.path.join(CORPUS, "copybooks", "01_alnum_basic.cpy")
PW = "s3cretPW-do-not-leak"
USERINFO_URLS = [
    f"http://alice:{PW}@registry.invalid",
    f"https://alice:{PW}@registry.invalid:8081/",
    f"https://alice:{PW}@[::1",
    f"http://{PW}@registry.invalid",
]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network/DNS used")
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.delenv("KOPYBOOK_REGISTRY_USER", raising=False)
    monkeypatch.delenv("KOPYBOOK_REGISTRY_PASSWORD", raising=False)


class FakeOpener:
    def __init__(self, exc=None):
        self.exc, self.req = exc, None

    def open(self, req, timeout):
        self.req = req
        if self.exc:
            raise self.exc
        return io.BytesIO(b'{"id":1}')


def run(monkeypatch, capsys, url, opener=None):
    opener = opener or FakeOpener()
    monkeypatch.setattr(cli.urllib.request, "build_opener", lambda *h: opener)
    rc = cli.main(["register", CB, "--registry", url, "--subject", "s-value"])
    out, err = capsys.readouterr()
    return rc, out + err, opener


@pytest.mark.parametrize("url", USERINFO_URLS)
def test_userinfo_refused_without_echo(monkeypatch, capsys, url):
    rc, text, opener = run(monkeypatch, capsys, url)
    assert rc == 64 and ("must not contain credentials" in text or "not a valid URL" in text)
    assert opener.req is None
    assert PW not in text and "alice" not in text and "registry.invalid" not in text


@pytest.mark.parametrize("url", USERINFO_URLS)
def test_userinfo_exception_and_traceback_clean(url):
    with pytest.raises(ValueError) as ei:
        cli._registry_request(url, "s", b"{}")
    tb = "".join(traceback.format_exception(ei.value))
    assert PW not in str(ei.value) and PW not in tb


STUB = ("import socket, sys\n"
        "def boom(*a, **k): raise SystemExit(99)\n"
        "socket.getaddrinfo = socket.create_connection = boom\n"
        "from kopybook.cli import main\n"
        "sys.exit(main(sys.argv[1:]))\n")


@pytest.mark.parametrize("url", USERINFO_URLS[:2])
def test_userinfo_subprocess_clean(url):
    env = dict(os.environ, PYTHONPATH=os.path.join(HERE, "..", "src"))
    env.pop("KOPYBOOK_REGISTRY_USER", None)
    env.pop("KOPYBOOK_REGISTRY_PASSWORD", None)
    p = subprocess.run([sys.executable, "-c", STUB, "register", CB, "--registry", url, "--subject", "s"],
                       capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 64  # 99 would mean a DNS lookup or connection was attempted
    assert PW not in p.stdout and PW not in p.stderr


def test_basic_auth_header_from_env(monkeypatch, capsys):
    monkeypatch.setenv("KOPYBOOK_REGISTRY_USER", "alice")
    monkeypatch.setenv("KOPYBOOK_REGISTRY_PASSWORD", PW)
    rc, text, opener = run(monkeypatch, capsys, "https://registry.invalid:8081/")
    assert rc == 0 and '{"id":1}' in text and PW not in text
    assert opener.req.full_url == "https://registry.invalid:8081/subjects/s-value/versions"
    assert opener.req.get_header("Authorization") == "Basic " + base64.b64encode(f"alice:{PW}".encode()).decode()


def test_no_auth_header_without_env(monkeypatch, capsys):
    rc, _, opener = run(monkeypatch, capsys, "http://localhost:8081")
    assert rc == 0 and opener.req.get_header("Authorization") is None


def test_credentials_refused_over_http(monkeypatch, capsys):
    monkeypatch.setenv("KOPYBOOK_REGISTRY_USER", "alice")
    monkeypatch.setenv("KOPYBOOK_REGISTRY_PASSWORD", PW)
    rc, text, opener = run(monkeypatch, capsys, "http://registry.invalid")
    assert rc == 64 and "plain http" in text and opener.req is None and PW not in text


def test_partial_credentials_refused(monkeypatch, capsys):
    monkeypatch.setenv("KOPYBOOK_REGISTRY_PASSWORD", PW)
    rc, text, opener = run(monkeypatch, capsys, "https://registry.invalid")
    assert rc == 64 and opener.req is None and PW not in text


@pytest.mark.parametrize("exc", [
    urllib.error.HTTPError(f"https://alice:{PW}@x/", 401, f"Unauthorized {PW}", {}, None),
    urllib.error.URLError(f"cannot resolve alice:{PW}@x"),
    TimeoutError(PW),
    ValueError(PW),
])
def test_request_errors_sanitized(monkeypatch, capsys, exc):
    monkeypatch.setenv("KOPYBOOK_REGISTRY_USER", "alice")
    monkeypatch.setenv("KOPYBOOK_REGISTRY_PASSWORD", PW)
    rc, text, _ = run(monkeypatch, capsys, "https://registry.invalid", FakeOpener(exc))
    assert rc == 69 and "error:" in text
    assert PW not in text and "registry.invalid" not in text
