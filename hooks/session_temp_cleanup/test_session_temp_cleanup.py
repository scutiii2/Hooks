import json
import tempfile
import time
import unittest
from pathlib import Path

import sqlite3

import session_temp_cleanup
from session_temp_cleanup import sweep, sweep_codex

A, B, C, D = ("%08x-0000-0000-0000-000000000000" % n for n in (1, 2, 3, 4))


class SweepTest(unittest.TestCase):
    def test_removes_only_orphans(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            temp, proj = t / "claude", t / "projects"
            (proj / "p").mkdir(parents=True)
            (proj / "p" / f"{A}.jsonl").write_text("{}")  # chat still exists
            for sid in (A, B, C, D):
                (temp / "x" / sid).mkdir(parents=True)
                (temp / "x" / sid / "f.txt").write_text("data")
            (temp / "x" / "scratchpad").mkdir()  # not a session id
            future = time.time() + 48 * 3600  # make every folder older than the grace period
            removed = sweep(temp, proj, current=C, now=future)
            self.assertEqual({p.name for p in removed}, {B, D})
            self.assertTrue((temp / "x" / A).exists() and (temp / "x" / C).exists())
            self.assertTrue((temp / "x" / "scratchpad").exists())
            self.assertFalse((temp / "x" / B).exists())

    def test_counts_freed_bytes(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "projects").mkdir()
            (t / "claude" / "x" / B).mkdir(parents=True)
            (t / "claude" / "x" / B / "f.txt").write_text("12345")
            session_temp_cleanup.freed[0] = 0
            sweep(t / "claude", t / "projects", now=time.time() + 48 * 3600)
            self.assertEqual(session_temp_cleanup.freed[0], 5)

    def test_app_store_ids_kept(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            store = t / "app" / "u" / "o"
            store.mkdir(parents=True)
            (t / "projects").mkdir()
            (store / "local_1.json").write_text(json.dumps({"cliSessionId": A, "priorCliSessionIds": [B]}))
            for sid in (A, B, C):
                (t / "claude" / "x" / sid).mkdir(parents=True)
            removed = sweep(t / "claude", t / "projects", now=time.time() + 99 * 3600, app_sessions=t / "app")
            self.assertEqual([p.name for p in removed], [C])

    def test_unreadable_store_deletes_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "app" / "u" / "o").mkdir(parents=True)
            (t / "projects").mkdir()
            (t / "app" / "u" / "o" / "local_1.json").write_text("{broken")
            (t / "claude" / "x" / C).mkdir(parents=True)
            self.assertEqual(sweep(t / "claude", t / "projects", now=time.time() + 99 * 3600, app_sessions=t / "app"), [])

    def test_recent_folder_kept(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "projects").mkdir()
            (t / "claude" / "x" / B).mkdir(parents=True)
            self.assertEqual(sweep(t / "claude", t / "projects"), [])

    def test_dry_run_deletes_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "projects").mkdir()
            (t / "claude" / "x" / B).mkdir(parents=True)
            removed = sweep(t / "claude", t / "projects", dry_run=True, now=time.time() + 99 * 3600)
            self.assertEqual(len(removed), 1)
            self.assertTrue((t / "claude" / "x" / B).exists())


class CodexSweepTest(unittest.TestCase):
    def make(self, t, threads):
        db = t / "state.sqlite"
        con = sqlite3.connect(db)
        con.execute("create table threads (id text)")
        con.executemany("insert into threads values (?)", [(x,) for x in threads])
        con.commit()
        con.close()
        for sid in (A, B, C):
            (t / "img" / sid).mkdir(parents=True)
        return db

    def test_removes_only_deleted_threads(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            db = self.make(t, [A])
            removed = sweep_codex(t / "img", db, current=C, now=time.time() + 99 * 3600)
            self.assertEqual([p.name for p in removed], [B])
            self.assertTrue((t / "img" / A).exists() and (t / "img" / C).exists())

    def test_empty_or_missing_db_deletes_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            db = self.make(t, [])
            self.assertEqual(sweep_codex(t / "img", db, now=time.time() + 99 * 3600), [])
            self.assertEqual(sweep_codex(t / "img", t / "none.sqlite", now=time.time() + 99 * 3600), [])


if __name__ == "__main__":
    unittest.main()
