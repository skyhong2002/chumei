import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import publish_site
import site_paths


class AtomicPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / "site"
        self.source.mkdir()
        (self.source / "index.html").write_text("template")
        (self.source / "asset.js").write_text("source asset")
        self.current = self.root / "published" / "current"
        self.previous = self.root / "published" / "previous"
        self.generation = 0

    def runner(self, script, stage):
        self.assertNotEqual(stage, self.source)
        if script == "build_site.py":
            (stage / "index.html").write_text(f"generation {self.generation}")
            (stage / "data.json").write_text(json.dumps({"generation": self.generation}))
        if script == "validate_outputs.py":
            self.assertEqual((stage / "index.html").read_text(), f"generation {self.generation}")
            self.assertEqual(json.loads((stage / "data.json").read_text())["generation"], self.generation)

    def publish(self):
        self.generation += 1
        return publish_site.publish(self.root, runner=self.runner)

    def snapshot(self):
        return {str(p.relative_to(self.current)): p.read_bytes()
                for p in self.current.rglob("*") if p.is_file()}

    def test_success_preserves_templates_and_caches_and_rolls_back(self):
        first = self.publish()
        (first / "historic.html").write_text("old event URL")
        initial = self.snapshot()
        (self.source / "asset.js").write_text("updated source asset")
        second = self.publish()
        self.assertEqual(self.current.resolve(), second)
        self.assertEqual(self.previous.resolve(), first)
        self.assertEqual((self.current / "historic.html").read_text(), "old event URL")
        self.assertEqual((self.current / "asset.js").read_text(), "updated source asset")
        self.assertEqual((self.source / "index.html").read_text(), "template")
        publish_site.rollback(self.root)
        self.assertEqual(self.snapshot(), initial)
        # A repeated rollback after an interrupted operator session is safe.
        self.assertEqual(publish_site.rollback(self.root), first)

    def test_failure_at_every_build_step_keeps_entire_current_release(self):
        first = self.publish()
        snapshot = self.snapshot()
        for failed_step in publish_site.BUILD_STEPS:
            with self.subTest(step=failed_step):
                def fail(script, stage):
                    (stage / "index.html").write_text("partial output")
                    (stage / "asset.js").write_text("partial asset")
                    # While every intermediate build step runs readers see old data.
                    self.assertEqual(self.snapshot(), snapshot)
                    if script == failed_step:
                        raise subprocess.CalledProcessError(1, script)
                with self.assertRaises(subprocess.CalledProcessError):
                    publish_site.publish(self.root, runner=fail)
                self.assertEqual(self.current.resolve(), first)
                self.assertEqual(self.snapshot(), snapshot)
                self.assertEqual(list((self.root / "published" / "releases").iterdir()), [first])

    def test_first_failed_publication_does_not_activate_drafts(self):
        with self.assertRaises(RuntimeError):
            publish_site.publish(self.root, runner=mock.Mock(side_effect=RuntimeError("bad build")))
        self.assertFalse(self.current.exists())
        self.assertEqual((self.source / "index.html").read_text(), "template")

    def test_current_pointer_replacement_failure_retains_old_release(self):
        first = self.publish()
        snapshot = self.snapshot()
        replace = os.replace
        def fail_current(src, dst):
            if dst == self.current:
                raise OSError("injected rename failure")
            return replace(src, dst)
        with mock.patch.object(publish_site.os, "replace", side_effect=fail_current):
            with self.assertRaises(OSError):
                self.publish()
        self.assertEqual(self.current.resolve(), first)
        self.assertEqual(self.snapshot(), snapshot)
        self.assertEqual(list((self.root / "published" / "releases").iterdir()), [first])
        self.assertFalse(list(self.current.parent.glob(".current-*")))

    def test_publication_and_rollback_refuse_concurrent_writer(self):
        self.publish()
        lock = self.root / "state" / "publish.lock"
        with publish_site.exclusive_lock(lock):
            for action in (self.publish, lambda: publish_site.rollback(self.root)):
                with self.assertRaisesRegex(RuntimeError, "Another job"):
                    action()
        self.publish()  # failure released all acquired resources

    def test_lock_is_visible_to_a_different_process(self):
        lock = self.root / "state" / "publish.lock"
        with publish_site.exclusive_lock(lock):
            code = "import sys;sys.path.insert(0,sys.argv[1]);from publish_site import exclusive_lock;from pathlib import Path\nwith exclusive_lock(Path(sys.argv[2])): pass"
            child = subprocess.run([sys.executable, "-c", code, str(Path(publish_site.__file__).parent), str(lock)], capture_output=True, text=True)
        self.assertNotEqual(child.returncode, 0)
        self.assertIn("Another job", child.stderr)

    def test_non_symlink_publication_target_is_never_overwritten(self):
        self.current.mkdir(parents=True)
        with self.assertRaisesRegex(RuntimeError, "non-symlink"):
            self.publish()
        self.assertTrue(self.current.is_dir())

    def test_runtime_reader_path_follows_releases_and_never_falls_back_if_broken(self):
        with mock.patch.object(site_paths, "ROOT", self.root):
            self.assertEqual(site_paths.published_site_dir(), self.source)
            first = self.publish()
            path = site_paths.published_site_dir() / "data.json"
            self.assertEqual(path.parent, self.current)
            self.publish()
            self.assertEqual(json.loads(path.read_text())["generation"], 2)
            self.current.unlink()
            self.current.symlink_to("missing-release")
            self.assertEqual(site_paths.published_site_dir(), self.current)

    def test_retention_protects_current_previous_and_unmanaged_directories(self):
        first = self.publish()
        second = self.publish()
        third = self.publish()
        fourth = self.publish()
        # Protect an older rollback target, in addition to the newest two.
        publish_site.atomic_link(self.previous, first)
        unmanaged = first.parent / "manual-backup"
        unmanaged.mkdir()
        staging = first.parent / ".staging-interrupted"
        staging.mkdir()
        removed = publish_site.prune(self.root, keep=2)
        self.assertEqual(removed, [second])
        for path in (first, third, fourth, unmanaged, staging):
            self.assertTrue(path.exists())
        self.assertEqual(self.current.resolve(), fourth)
        self.assertEqual(self.previous.resolve(), first)

    def test_all_build_outputs_use_staging_in_a_real_child_process(self):
        stage = self.root / "stage"
        env = dict(os.environ, CHUMEI_BUILD_DIR=str(stage), CHUMEI_BUILD_OFFLINE="1")
        code = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import build_site, build_map_data, build_status_page, chumei_lib, render_source_covers, validate_outputs
stage = Path(sys.argv[2])
paths = [build_site.SITE, build_site.POSTER_DIR, build_site.POST_IMG_DIR,
         build_map_data.OUT, build_status_page.OUT_API, build_status_page.OUT_PAGE,
         chumei_lib.AVATAR_DIR, render_source_covers.OUTPUT_DIR, validate_outputs.SITE]
assert all(path == stage or stage in path.parents for path in paths), paths
"""
        result = subprocess.run([sys.executable, "-c", code, str(Path(publish_site.__file__).parent), str(stage)], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def make_copy_fixture(self):
        source, target = self.root / "copy-source", self.root / "copy-target"
        (source / "nested").mkdir(parents=True)
        (source / "nested" / "page.html").write_text("source page")
        (source / "shared.txt").write_text("source shared")
        (source / "link.txt").symlink_to("shared.txt")
        target.mkdir()
        (target / "shared.txt").write_text("stale shared")
        (target / "historic.html").write_text("historic")
        return source, target

    def assert_independent_overlay(self, source, target):
        self.assertEqual((target / "nested" / "page.html").read_text(), "source page")
        self.assertEqual((target / "shared.txt").read_text(), "source shared")
        self.assertEqual((target / "historic.html").read_text(), "historic")
        # Like copytree(symlinks=False), symlinks become regular files.
        self.assertFalse((target / "link.txt").is_symlink())
        self.assertEqual((target / "link.txt").read_text(), "source shared")
        for name in ("nested/page.html", "shared.txt"):
            self.assertNotEqual((source / name).stat().st_ino, (target / name).stat().st_ino)
        # Later writes to either tree must never reach the other.
        (target / "shared.txt").write_text("stage rewrite")
        with (target / "nested" / "page.html").open("a") as handle:
            handle.write(" + stage append")
        (source / "link.txt").unlink()
        (source / "shared.txt").write_text("source rewrite")
        self.assertEqual((source / "nested" / "page.html").read_text(), "source page")
        self.assertEqual((target / "shared.txt").read_text(), "stage rewrite")
        self.assertEqual((target / "link.txt").read_text(), "source shared")

    def test_copy_tree_overlays_independent_files(self):
        source, target = self.make_copy_fixture()
        publish_site.copy_tree(source, target)
        self.assert_independent_overlay(source, target)

    @unittest.skipUnless(sys.platform == "darwin", "APFS clones are only attempted on macOS")
    def test_copy_tree_uses_clone_copy_on_macos(self):
        source, target = self.make_copy_fixture()
        with mock.patch.object(publish_site.shutil, "copytree") as copytree:
            publish_site.copy_tree(source, target)
        copytree.assert_not_called()
        self.assert_independent_overlay(source, target)

    def test_copy_tree_falls_back_to_full_copy_when_cloning_fails(self):
        source, target = self.make_copy_fixture()
        failed = subprocess.CompletedProcess([], 1, stderr="cp: clonefile failed")
        with mock.patch.object(publish_site.sys, "platform", "darwin"), \
             mock.patch.object(publish_site.subprocess, "run", return_value=failed) as run, \
             mock.patch("sys.stderr"):
            publish_site.copy_tree(source, target)
        self.assertIn("-c", run.call_args.args[0])
        self.assert_independent_overlay(source, target)

    def test_subprocess_receives_isolated_output_and_offline_flag(self):
        with mock.patch.object(publish_site.subprocess, "run") as run:
            publish_site.run_build_step("build_site.py", self.root / "stage", self.root, offline=True)
        self.assertEqual(run.call_args.kwargs["env"]["CHUMEI_BUILD_DIR"], str(self.root / "stage"))
        self.assertEqual(run.call_args.kwargs["env"]["CHUMEI_BUILD_OFFLINE"], "1")
        self.assertTrue(run.call_args.kwargs["check"])
        self.assertEqual(run.call_args.kwargs["timeout"], publish_site.STEP_TIMEOUT)

    def test_build_limits_stay_below_pipeline_step_limit(self):
        # run_pipeline SIGKILLs publish_site.py after 7200s, which would orphan staging.
        self.assertLess(publish_site.STEP_TIMEOUT, publish_site.PUBLISH_BUDGET)
        self.assertLessEqual(publish_site.PUBLISH_BUDGET, 7200 / 2)

    def test_default_runner_caps_each_step_by_remaining_budget(self):
        clock = iter([0, 0, publish_site.PUBLISH_BUDGET - 60, publish_site.PUBLISH_BUDGET])
        with mock.patch.object(publish_site.time, "monotonic", side_effect=lambda: next(clock)), \
             mock.patch.object(publish_site, "run_build_step") as step:
            with self.assertRaises(subprocess.TimeoutExpired) as raised:
                publish_site.publish(self.root)
        self.assertEqual(raised.exception.cmd, publish_site.BUILD_STEPS[2])
        self.assertEqual([call.kwargs["timeout"] for call in step.call_args_list],
                         [publish_site.STEP_TIMEOUT, 60])
        self.assertFalse(self.current.exists())
        self.assertEqual(list((self.root / "published" / "releases").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
