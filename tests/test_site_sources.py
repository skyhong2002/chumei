import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import site_sources


class SiteSourceSyncTests(unittest.TestCase):
    """The repository's site/ is hidden behind a mounted directory in production."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git("init", "-q")
        self.write("site/app.js", "v1")
        self.write("site/old.html", "old")
        self.write("site/avatars/a.jpg", "committed avatar")
        self.write("scripts/tool.py", "v1")
        self.first = self.commit("first")
        (self.root / "state").mkdir()
        mounted = mock.patch.object(Path, "is_mount", return_value=True)
        mounted.start()
        self.addCleanup(mounted.stop)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@example.org",
                               "-c", "commit.gpgsign=false", *args], check=True, capture_output=True, text=True).stdout

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD").strip()

    def read(self, name):
        return (self.root / name).read_text()

    def sync(self):
        with mock.patch("builtins.print"):
            return site_sources.sync_site_sources(self.root)

    def advance_repository(self):
        """Commit new sources, then put the mounted directory back to its stale state."""
        self.write("site/app.js", "v2")
        self.write("site/new/page.html", "new")
        (self.root / "site/old.html").unlink()
        head = self.commit("second")
        self.write("site/app.js", "v1")
        self.write("site/old.html", "old")
        (self.root / "site/new/page.html").unlink()
        return head

    def test_first_run_only_records_the_revision(self):
        self.write("site/app.js", "runtime copy")
        self.assertEqual(self.sync(), (0, 0))
        self.assertEqual(self.read("site/app.js"), "runtime copy")
        self.assertEqual(self.read("state/site_source_revision").strip(), self.first)

    def test_applies_repository_changes_and_keeps_runtime_files(self):
        self.sync()
        head = self.advance_repository()
        self.write("site/avatars/a.jpg", "refreshed at runtime")
        self.write("site/api/status.json", "generated")
        self.assertEqual(self.sync(), (2, 1))
        self.assertEqual(self.read("site/app.js"), "v2")
        self.assertEqual(self.read("site/new/page.html"), "new")
        self.assertFalse((self.root / "site/old.html").exists())
        self.assertEqual(self.read("site/avatars/a.jpg"), "refreshed at runtime")
        self.assertEqual(self.read("site/api/status.json"), "generated")
        self.assertEqual(self.read("state/site_source_revision").strip(), head)
        self.assertEqual(self.sync(), (0, 0))

    def test_working_tree_site_is_left_to_git(self):
        self.sync()
        self.advance_repository()
        with mock.patch.object(Path, "is_mount", return_value=False):
            self.assertEqual(self.sync(), (0, 0))
        self.assertEqual(self.read("site/app.js"), "v1")

    def test_unknown_recorded_revision_warns_without_touching_files(self):
        self.write("state/site_source_revision", "0" * 40 + "\n")
        with mock.patch("builtins.print") as output:
            self.assertEqual(site_sources.sync_site_sources(self.root), (0, 0))
        self.assertIs(output.call_args.kwargs["file"], sys.stderr)
        self.assertIn("not synchronised", output.call_args.args[0])
        self.assertEqual(self.read("site/app.js"), "v1")
        self.assertEqual(self.read("state/site_source_revision").strip(), "0" * 40)


if __name__ == "__main__":
    unittest.main()
