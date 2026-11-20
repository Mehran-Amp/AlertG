# -*- coding: utf-8 -*-
"""IB-18b: behaviour tests of scripts/aegkala/tse-forward.php (the Iranian-host bridge for the Bourse gateway).

The PHP file runs under PHP's built-in web server against a mock TSETMC (no real network). Skipped when
no `php` binary is installed.
"""
import gzip
import http.client
import json
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

PHP = shutil.which("php")
pytestmark = pytest.mark.skipif(PHP is None, reason="php is not installed")

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "aegkala" / "tse-forward.php"
TOKEN = "T0kenForTestsOnly1234567890abcd"
PAYLOAD = ("سهام;فولاد;1000;@" * 50 + "عیار;668761").encode("utf-8")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Upstream:
    """Mock old.tsetmc.com/tsev2/data."""

    def __init__(self):
        self.hits = []          # (path, query, accept-encoding)
        self.mode = "ok"        # ok | 500 | big
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                path, _, query = self.path.partition("?")
                ae = self.headers.get("Accept-Encoding", "")
                outer.hits.append((path, query, ae))
                if outer.mode == "500":
                    self.send_response(500); self.end_headers(); return
                body = PAYLOAD * (3000 if outer.mode == "big" else 1)
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                if "gzip" in ae:
                    body = gzip.compress(body)
                    self.send_header("Content-Encoding", "gzip")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.port = free_port()
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        if getattr(self, "_stopped", False):
            return
        self._stopped = True
        self.server.shutdown()
        self.server.server_close()      # really close the port: connections are refused afterwards


class Bridge:
    def __init__(self, upstream: Upstream, **cfg):
        self.dir = Path(tempfile.mkdtemp(prefix="tse_fwd_"))
        shutil.copy(SCRIPT, self.dir / "tse-forward.php")
        config = {"token": TOKEN, "allow_ips": [], "base_url": f"http://127.0.0.1:{upstream.port}/tsev2/data"}
        config.update(cfg)
        if config.get("token") is None:
            del config["token"]
        (self.dir / "tse-forward.config.php").write_text("<?php return " + php_array(config) + ";")
        self.port = free_port()
        self.proc = subprocess.Popen([PHP, "-S", f"127.0.0.1:{self.port}", "-t", str(self.dir)],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", self.port), 0.2).close()
                break
            except OSError:
                time.sleep(0.1)

    def get(self, path, headers=None, method="GET"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        c.request(method, "/tse-forward.php" + path, headers=headers or {"Accept-Encoding": "identity"})
        r = c.getresponse()
        body = r.read()
        hdr = {k.lower(): v for k, v in r.getheaders()}
        c.close()
        return r.status, hdr, body

    def stop(self):
        self.proc.terminate()
        self.proc.wait(5)
        shutil.rmtree(self.dir, ignore_errors=True)


def php_array(d):
    return json.dumps(d).replace("{", "[").replace("}", "]").replace('":', '" =>')


@pytest.fixture()
def up():
    u = Upstream()
    yield u
    u.stop()


@pytest.fixture()
def bridge(up):
    b = Bridge(up)
    yield b
    b.stop()


INIT = f"/{TOKEN}/MarketWatchInit.aspx?h=0&r=0"
PLUS = f"/{TOKEN}/MarketWatchPlus.aspx?h=0&r=123"


def test_plain_passthrough(bridge, up):
    st, h, body = bridge.get(INIT)
    assert st == 200
    assert body == PAYLOAD
    assert h["content-type"].startswith("text/csv")
    assert h["x-source"] == "upstream"
    assert up.hits[0][0] == "/tsev2/data/MarketWatchInit.aspx"
    assert up.hits[0][1] == "h=0&r=0"


def test_plus_parameters_are_forwarded(bridge, up):
    st, _, body = bridge.get(PLUS)
    assert st == 200 and body == PAYLOAD
    assert up.hits[0][0] == "/tsev2/data/MarketWatchPlus.aspx"
    assert up.hits[0][1] == "h=0&r=123"


def test_gzip_is_passed_through_untouched(bridge, up):
    st, h, body = bridge.get(INIT, {"Accept-Encoding": "gzip"})
    assert st == 200
    assert h.get("content-encoding") == "gzip"
    assert gzip.decompress(body) == PAYLOAD
    assert len(body) < len(PAYLOAD)


def test_client_without_gzip_gets_plain_even_if_upstream_could_gzip(bridge, up):
    st, h, body = bridge.get(INIT, {"Accept-Encoding": "identity"})
    assert "content-encoding" not in h
    assert body == PAYLOAD


def test_micro_cache_collapses_close_requests(bridge, up):
    bridge.get(INIT)
    st, h, body = bridge.get(INIT)
    assert st == 200 and body == PAYLOAD
    assert h["x-source"] == "cache"
    assert len(up.hits) == 1


def test_cache_can_be_off(up):
    b = Bridge(up, cache_seconds=0)
    try:
        b.get(INIT); b.get(INIT)
        assert len(up.hits) == 2
    finally:
        b.stop()


def test_different_parameters_are_not_mixed_up_by_the_cache(bridge, up):
    bridge.get(INIT)
    bridge.get(PLUS)
    assert len(up.hits) == 2


def test_wrong_token_is_401_and_upstream_is_not_touched(bridge, up):
    st, _, _ = bridge.get("/wrong-token/MarketWatchInit.aspx?h=0&r=0")
    assert st == 401
    assert up.hits == []


def test_caller_ip_not_in_the_allow_list_is_403(up):
    b = Bridge(up, allow_ips=["203.0.113.9"])
    try:
        st, _, _ = b.get(INIT)
        assert st == 403
        assert up.hits == []
    finally:
        b.stop()


def test_allowed_caller_ip_passes(up):
    b = Bridge(up, allow_ips=["127.0.0.1"])
    try:
        assert b.get(INIT)[0] == 200
    finally:
        b.stop()


@pytest.mark.parametrize("path", [
    f"/{TOKEN}/passwd",
    f"/{TOKEN}/MarketWatchInit.aspx.bak",
    f"/{TOKEN}/../MarketWatchInit.aspx",
    f"/{TOKEN}/MarketWatch.aspx",
    f"/{TOKEN}/sub/MarketWatchInit.aspx",
    f"/{TOKEN}",
    "",
])
def test_only_the_two_feed_files_are_reachable(bridge, up, path):
    st, _, _ = bridge.get(path + "?h=0&r=0")
    assert st in (401, 404)
    assert up.hits == []


@pytest.mark.parametrize("q", [
    "h=abc&r=0",
    "h=0&r=1;2",
    "h=-1&r=0",
    "h=0&r=",
    "h=%27&r=0",
    "h=9999999999999999999&r=0",
    "h=0&r=9999999999999999999",
])
def test_parameters_must_be_digits(bridge, up, q):
    st, _, _ = bridge.get(f"/{TOKEN}/MarketWatchPlus.aspx?{q}")
    assert st == 400
    assert up.hits == []


@pytest.mark.parametrize("q", [
    "h=182939&r=16498993143",
    "h=0&r=999999999999999999",
])
def test_large_refid_up_to_18_digits_is_forwarded(bridge, up, q):
    st, hdr, body = bridge.get(f"/{TOKEN}/MarketWatchPlus.aspx?{q}")
    assert st == 200
    assert body == PAYLOAD
    assert hdr.get("x-bridge") == "tse-forward/1.1"
    assert up.hits[0][0] == "/tsev2/data/MarketWatchPlus.aspx"
    assert up.hits[0][1] == q


def test_missing_parameters_default_to_zero(bridge, up):
    st, _, _ = bridge.get(f"/{TOKEN}/MarketWatchInit.aspx")
    assert st == 200
    assert up.hits[0][1] == "h=0&r=0"


def test_extra_query_values_are_not_forwarded(bridge, up):
    bridge.get(f"/{TOKEN}/MarketWatchInit.aspx?h=0&r=0&url=http://evil.example/&x=1")
    assert up.hits[0][1] == "h=0&r=0"


def test_post_is_refused(bridge, up):
    st, _, _ = bridge.get(INIT, method="POST")
    assert st == 405
    assert up.hits == []


def test_upstream_error_becomes_502_and_is_not_cached(bridge, up):
    up.mode = "500"
    st, _, _ = bridge.get(INIT)
    assert st == 502
    up.mode = "ok"
    st, _, body = bridge.get(INIT)
    assert st == 200 and body == PAYLOAD


def test_oversized_upstream_is_cut_off(up):
    up.mode = "big"
    b = Bridge(up, max_bytes=1000)
    try:
        st, _, _ = b.get(INIT)
        assert st == 502
    finally:
        b.stop()


def test_unreachable_upstream_is_502(up):
    port = up.port
    up.stop()
    b = Bridge(up)
    try:
        st, _, _ = b.get(INIT)
        assert st == 502
    finally:
        b.stop()


def test_unconfigured_or_weak_token_is_500(up):
    for token in (None, "short"):
        b = Bridge(up, token=token)
        try:
            assert b.get(INIT)[0] == 500
            assert up.hits == []
        finally:
            b.stop()


def test_url_shape_the_gateway_builds_works(bridge, up):
    """The gateway does: base_url + '/MarketWatchInit.aspx?h=0&r=0' with base_url ending in the token."""
    base = f"/{TOKEN}"
    st, _, _ = bridge.get(base + "/MarketWatchInit.aspx?h=0&r=0")
    assert st == 200
