"""Self-check for source_of_truth.py. Run: py -m unittest test_source_of_truth (from this folder)."""
import os
import tempfile
import unittest
from pathlib import Path

import source_of_truth as h


def can_symlink() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.symlink("x", Path(tmp) / "l", target_is_directory=True)
            return True
        except OSError:
            return False


@unittest.skipUnless(can_symlink(), "symlinks not available")
class SourceOfTruthTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.project = self.root / "proj"
        (self.project / ".git").mkdir(parents=True)
        self.codex = self.root / "codex-skills"
        self.codex.mkdir()
        self._saved_codex, h.CODEX_SKILLS = h.CODEX_SKILLS, self.codex  # never touch the real ~/.codex

    def tearDown(self):
        h.CODEX_SKILLS = self._saved_codex
        self._tmp.cleanup()

    def run_hook(self, event="SessionStart"):
        return h.run(self.project, event, [self.root])

    def test_claude_skills_moved_and_linked(self):
        skill = self.project / ".claude" / "skills" / "demo"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("demo")
        self.assertIsNotNone(self.run_hook())
        self.assertTrue((self.project / ".claude" / "skills").is_symlink())
        self.assertEqual((self.project / ".agents" / "skills" / "demo" / "SKILL.md").read_text(), "demo")
        self.assertEqual((self.project / ".claude" / "skills" / "demo" / "SKILL.md").read_text(), "demo")

    def test_agents_skills_get_link(self):
        (self.project / ".agents" / "skills" / "demo").mkdir(parents=True)
        self.run_hook()
        self.assertTrue((self.project / ".claude" / "skills" / "demo").is_dir())

    def test_both_real_is_left_alone_and_warned(self):
        (self.project / ".claude" / "skills" / "a").mkdir(parents=True)
        (self.project / ".agents" / "skills" / "b").mkdir(parents=True)
        out = self.run_hook()
        self.assertIn("merge by hand", out["hookSpecificOutput"]["additionalContext"])
        self.assertTrue((self.project / ".claude" / "skills" / "a").is_dir())
        self.assertFalse((self.project / ".claude" / "skills").is_symlink())
        self.assertIsNone(self.run_hook("PostToolUse"))  # warnings only on SessionStart

    def test_claude_md_rules_move_to_agents_md(self):
        (self.project / "CLAUDE.md").write_text("# Rules\nbe nice\n")
        self.run_hook()
        self.assertEqual((self.project / "AGENTS.md").read_text(), "# Rules\nbe nice\n")
        self.assertEqual((self.project / "CLAUDE.md").read_text().strip(), "@AGENTS.md")

    def test_agents_md_gets_stub(self):
        (self.project / "AGENTS.md").write_text("rules")
        self.run_hook()
        self.assertEqual((self.project / "CLAUDE.md").read_text().strip(), "@AGENTS.md")

    def test_differing_rules_are_kept(self):
        (self.project / "AGENTS.md").write_text("one")
        (self.project / "CLAUDE.md").write_text("two")
        self.run_hook()
        self.assertEqual((self.project / "CLAUDE.md").read_text(), "two")
        self.assertEqual((self.project / "AGENTS.md").read_text(), "one")

    def test_idempotent_and_empty_project_untouched(self):
        self.assertIsNone(self.run_hook())
        (self.project / "AGENTS.md").write_text("rules")
        self.run_hook()
        self.assertIsNone(self.run_hook())

    def test_outside_root_untouched(self):
        (self.project / "CLAUDE.md").write_text("rules")
        self.assertIsNone(h.run(self.project, "SessionStart", [self.root / "elsewhere"]))
        self.assertFalse((self.project / "AGENTS.md").exists())

    def test_each_skill_is_linked_into_codex_and_a_real_folder_is_kept(self):
        for name in ("alpha", "beta"):
            (self.project / ".agents" / "skills" / name).mkdir(parents=True)
            (self.project / ".agents" / "skills" / name / "SKILL.md").write_text("x")
        (self.project / ".agents" / "skills" / "notes").mkdir()  # no SKILL.md: not a skill
        (self.codex / "beta").mkdir()
        out = self.run_hook()["hookSpecificOutput"]["additionalContext"]
        self.assertTrue((self.codex / "alpha").is_symlink())
        self.assertFalse((self.codex / "beta").is_symlink())
        self.assertFalse((self.codex / "notes").exists())
        self.assertIn("beta: ~/.codex/skills has a real folder", out)
        self.assertEqual((self.codex / "alpha" / "SKILL.md").read_text(), "x")


if __name__ == "__main__":
    unittest.main()
