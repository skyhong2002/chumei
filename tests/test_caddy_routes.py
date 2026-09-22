"""Exercise the production vhost with isolated Caddy and upstream processes.

Uses local ports 18991/18992 and never connects to the production admin endpoint.
"""
import http.client
import http.server
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
CADDY = shutil.which("caddy") or ("/usr/local/sbin/caddy" if Path("/usr/local/sbin/caddy").exists() else None)


class Upstream(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(("upstream:" + self.path).encode())

    def log_message(self, *args):
        pass


@unittest.skipUnless(CADDY, "Caddy binary required for HTTP routing integration tests")
class CaddyRoutesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="chumei-caddy-test-")
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(cls.tmp.name)
        site = root / "site"
        for path, content in {
            "index.html": "known homepage",
            "events/index.html": "known events",
            "event/known/index.html": "known event",
            "event/merged/index.html": '<meta http-equiv="refresh" content="0;url=/event/known/">',
            "assets/app.js": "/* known javascript */",
            "feeds/all.ics": "BEGIN:VCALENDAR",
            "404.html": (ROOT / "site/404.html").read_text(),
        }.items():
            target = site / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        config = (ROOT / "deploy/chumei.caddy").read_text()
        config = config.replace("chumei.observe.tw {", "http://127.0.0.1:18991 {")
        config = config.replace("/Users/skyhong/Projects/chumei/published/current", str(site))
        for port in (8321, 8322, 8323, 8324):
            config = config.replace(f"127.0.0.1:{port}", "127.0.0.1:18992")
        path = root / "Caddyfile"
        path.write_text("{\n admin off\n auto_https off\n}\n" + config)
        cls.upstream = http.server.ThreadingHTTPServer(("127.0.0.1", 18992), Upstream)
        cls.addClassCleanup(cls.upstream.server_close)
        cls.addClassCleanup(cls.upstream.shutdown)
        threading.Thread(target=cls.upstream.serve_forever, daemon=True).start()
        env = {**os.environ, "XDG_CONFIG_HOME": str(root / "config"), "XDG_DATA_HOME": str(root / "data")}
        cls.log = (root / "caddy.log").open("w+")
        cls.addClassCleanup(cls.log.close)
        cls.proc = subprocess.Popen([CADDY, "run", "--config", str(path), "--adapter", "caddyfile"], env=env, stdout=cls.log, stderr=cls.log)
        cls.addClassCleanup(cls.stop_caddy)
        for _ in range(100):
            if cls.proc.poll() is not None:
                cls.log.seek(0)
                raise RuntimeError(cls.log.read())
            try:
                cls.request("/")
                break
            except OSError:
                time.sleep(.05)
        else:
            raise RuntimeError("Isolated Caddy did not start")

    @classmethod
    def stop_caddy(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
            cls.proc.wait()

    @classmethod
    def request(cls, path, method="GET", accept="text/html"):
        conn = http.client.HTTPConnection("127.0.0.1", 18991, timeout=2)
        try:
            conn.request(method, path, headers={"Accept": accept})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read().decode()
        finally:
            conn.close()

    def test_known_static_and_merged_pages(self):
        for path, expected in (("/", "known homepage"), ("/events/", "known events"), ("/event/known/", "known event"), ("/event/merged/", "url=/event/known/"), ("/assets/app.js", "known javascript"), ("/feeds/all.ics", "BEGIN:VCALENDAR")):
            with self.subTest(path=path):
                status, _, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertIn(expected, body)
        status, headers, _ = self.request("/events")
        self.assertEqual(status, 308)
        self.assertEqual(headers["Location"], "/events/")

    def test_missing_pages_have_real_404_and_recovery_links(self):
        for path in ("/not-a-page", "/event/not-an-event/", "/missing.html"):
            with self.subTest(path=path):
                status, headers, body = self.request(path)
                self.assertEqual(status, 404)
                self.assertIn("text/html", headers["Content-Type"])
                self.assertEqual(headers["X-Robots-Tag"], "noindex")
                self.assertIn('name="robots" content="noindex"', body)
                self.assertIn('action="/events/"', body)
                self.assertIn('href="/"', body)
                self.assertNotIn("known homepage", body)
        self.assertEqual(self.request("/missing", method="HEAD")[0], 404)

    def test_missing_assets_are_never_html(self):
        for path in ("/assets/missing.js", "/assets/missing", "/missing.js", "/data/missing.json", "/feeds/missing.ics", "/sw.js", "/manifest.webmanifest"):
            with self.subTest(path=path):
                status, headers, body = self.request(path)
                self.assertEqual(status, 404)
                self.assertIn("text/plain", headers["Content-Type"])
                self.assertEqual(body, "Not found")

    def test_dynamic_routes_keep_original_path(self):
        for path in ("/mcp", "/mcp/tools", "/line/webhook", "/push/subscribe", "/auth/login", "/account", "/account/", "/submit", "/submit/", "/contribute", "/contribute/", "/@someone", "/feeds/custom.ics?schools=nthu", "/feeds/custom.xml", "/feeds/s/test.ics"):
            with self.subTest(path=path):
                status, _, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertEqual(body, "upstream:" + path)


if __name__ == "__main__":
    unittest.main()
