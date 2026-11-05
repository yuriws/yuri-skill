"""Regression tests for skill validation and chapter integrity (standard library only)."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOLS = Path(os.environ.get('SKILL_TOOLS_ROOT', Path(__file__).resolve().parent))
GUARDS = ['未成年角色排除在感情线外。', '不产出露骨性描写。', '公开发布须确认授权。', '幼态成年角色标注成年。']


def chapter(number, title='正文', body='章节内容'):
    return f'## 第{number}章《{title}》\n{body}\n'


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='novel-skill-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_tool(self, path, *args):
        return subprocess.run([sys.executable, str(path), *args], cwd=self.root,
                              capture_output=True, text=True, encoding='utf-8',
                              env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})


class VerifyTests(WorkspaceTest):
    def setUp(self):
        super().setUp()
        (self.root / 'scripts').mkdir()
        (self.root / 'references').mkdir()
        for name in ('verify.py', 'build-merged.py'):
            shutil.copy2(TOOLS / name, self.root / 'scripts' / name)
        self.skill = self.root / 'SKILL.md'
        self.rules = self.root / 'references' / 'rules.md'
        self.checklist = self.root / 'references' / 'checklist.md'
        self.skill.write_text('# Skill\n[规则](references/rules.md)\n\n| 规则 | 内容 |\n|---|---|\n| 4.1 | 事实 |\n| 4.10 | 护栏 |\n\n**硬护栏（不可协商）**：' + '；'.join(GUARDS) + '\n', encoding='utf-8')
        self.rules.write_text('## 4.1 事实\n事实。\n\n## 4.10 护栏\n\n' + '\n'.join(f'{i}. {g}' for i, g in enumerate(GUARDS, 1)) + '\n', encoding='utf-8')
        self.checklist.write_text('## 模板\n```\n# 第 N 批批尾体检\n```\n', encoding='utf-8')

    def verify(self):
        return self.run_tool(self.root / 'scripts' / 'verify.py')

    def test_valid_skill_passes(self):
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_wrong_rule_id_same_row_count_fails(self):
        self.skill.write_text(self.skill.read_text(encoding='utf-8').replace('| 4.1 |', '| 4.999 |'), encoding='utf-8')
        self.assertNotEqual(self.verify().returncode, 0)

    def test_duplicate_rule_id_fails(self):
        self.skill.write_text(self.skill.read_text(encoding='utf-8').replace('| 4.10 |', '| 4.1 |'), encoding='utf-8')
        self.assertNotEqual(self.verify().returncode, 0)

    def test_guard_content_drift_same_count_fails(self):
        self.skill.write_text(self.skill.read_text(encoding='utf-8').replace(GUARDS[1], '任意不同的护栏。'), encoding='utf-8')
        self.assertNotEqual(self.verify().returncode, 0)

    def test_missing_relative_reference_fails(self):
        self.checklist.write_text(self.checklist.read_text(encoding='utf-8') + '[细则](absent.md)\n', encoding='utf-8')
        self.assertNotEqual(self.verify().returncode, 0)

    def test_two_templates_in_same_file_fail(self):
        self.checklist.write_text(self.checklist.read_text(encoding='utf-8') * 2, encoding='utf-8')
        self.assertNotEqual(self.verify().returncode, 0)

    def test_verification_does_not_create_pycache(self):
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(list(self.root.rglob('__pycache__')), [])

    def test_duplicate_rule_heading_fails(self):
        self.rules.write_text(self.rules.read_text(encoding='utf-8') + '\n## 4.1 重复\n', encoding='utf-8')
        self.assertNotEqual(self.verify().returncode, 0)

    def test_guard_formatting_and_terminal_punctuation_are_ignored(self):
        self.rules.write_text(self.rules.read_text(encoding='utf-8').replace(GUARDS[0], '**未成年角色排除在感情线外**'), encoding='utf-8')
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_template_mentions_are_not_duplicate_templates(self):
        self.skill.write_text(self.skill.read_text(encoding='utf-8') + '\n参见“第 N 批批尾体检”。\n', encoding='utf-8')
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_reference_style_link_fails(self):
        self.checklist.write_text(self.checklist.read_text(encoding='utf-8') + '\n[细则][rules]\n[rules]: missing.md\n', encoding='utf-8')
        self.assertNotEqual(self.verify().returncode, 0)

    def test_existing_link_with_fragment_and_external_url_passes(self):
        self.checklist.write_text(self.checklist.read_text(encoding='utf-8') + '\n[规则](rules.md#规则) [网站](https://example.invalid/remote)\n', encoding='utf-8')
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ChapterTests(WorkspaceTest):
    def setUp(self):
        super().setUp()
        self.text = self.root / 'text'
        self.text.mkdir()
        self.script = self.root / 'build-merged.py'
        shutil.copy2(TOOLS / 'build-merged.py', self.script)

    def put(self, name, content):
        path = self.text / name
        path.write_text(content, encoding='utf-8')
        return path

    def merge(self, *args):
        return self.run_tool(self.script, *args)

    def generated(self):
        return list(self.text.glob('merged-*.md'))

    def test_loose_merge_sorts_chapter_numbers(self):
        self.put('002.md', chapter(2, body='第二章'))
        self.put('001.md', chapter(1, body='第一章'))
        result = self.merge()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = self.generated()[0].read_text(encoding='utf-8')
        self.assertLess(output.index('第一章'), output.index('第二章'))

    def test_volume_merge_ignores_excerpt_files(self):
        self.put('vol-001.md', '# 卷一\n\n' + chapter(1, body='唯一正文'))
        self.put('vol-001-ch001-010.md', chapter(1, body='摘录内容'))
        result = self.merge()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = self.generated()[0].read_text(encoding='utf-8')
        self.assertEqual(output.count('唯一正文'), 1)
        self.assertNotIn('摘录内容', output)

    def test_mixed_sources_fail_without_generated_file(self):
        self.put('vol-001.md', chapter(1))
        self.put('002.md', chapter(2))
        self.assertNotEqual(self.merge().returncode, 0)
        self.assertEqual(self.generated(), [])

    def test_gap_fails_without_generated_file(self):
        self.put('vol-001.md', chapter(1) + '\n' + chapter(3))
        self.assertNotEqual(self.merge().returncode, 0)
        self.assertEqual(self.generated(), [])

    def test_duplicate_chapter_number_fails(self):
        self.put('vol-001.md', chapter(1, title='旧') + '\n' + chapter(1, title='新'))
        self.assertNotEqual(self.merge().returncode, 0)

    def test_chapter_in_wrong_volume_fails(self):
        self.put('vol-001.md', chapter(101))
        self.assertNotEqual(self.merge().returncode, 0)

    def test_source_without_heading_fails(self):
        self.put('001.md', '没有章标题的正文\n')
        self.assertNotEqual(self.merge().returncode, 0)
        self.assertEqual(self.generated(), [])

    def test_filename_heading_mismatch_fails(self):
        self.put('001.md', chapter(2))
        self.assertNotEqual(self.merge().returncode, 0)

    def test_archive_is_idempotent_and_preserves_loose_sources(self):
        source = self.put('001.md', chapter(1))
        first = self.merge('--archive')
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        volume = self.text / 'vol-001.md'
        before = volume.read_bytes()
        second = self.merge('--archive')
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(volume.read_bytes(), before)
        self.assertTrue(source.exists())

    def test_same_number_new_title_conflicts_without_writing(self):
        volume = self.put('vol-001.md', chapter(1, title='旧标题'))
        self.put('001.md', chapter(1, title='新标题'))
        before = volume.read_bytes()
        self.assertNotEqual(self.merge('--archive').returncode, 0)
        self.assertEqual(volume.read_bytes(), before)

    def test_same_number_changed_body_conflicts_without_writing(self):
        volume = self.put('vol-001.md', chapter(1, body='原稿'))
        self.put('001.md', chapter(1, body='修改稿'))
        before = volume.read_bytes()
        self.assertNotEqual(self.merge('--archive').returncode, 0)
        self.assertEqual(volume.read_bytes(), before)

    def test_backfill_does_not_append_out_of_order(self):
        volume = self.put('vol-001.md', chapter(1) + '\n' + chapter(3))
        self.put('002.md', chapter(2))
        before = volume.read_bytes()
        self.assertNotEqual(self.merge('--archive').returncode, 0)
        self.assertEqual(volume.read_bytes(), before)

    def test_late_validation_failure_writes_no_earlier_volume(self):
        first = self.put('vol-001.md', '\n'.join(chapter(i) for i in range(1, 101)))
        second = self.put('vol-002.md', chapter(101))
        self.put('102.md', chapter(102))
        self.put('201.md', chapter(202))
        before = (first.read_bytes(), second.read_bytes())
        self.assertNotEqual(self.merge('--archive').returncode, 0)
        self.assertEqual((first.read_bytes(), second.read_bytes()), before)
        self.assertFalse((self.text / 'vol-003.md').exists())

    def test_partial_project_can_begin_above_one(self):
        self.put('vol-002.md', chapter(105) + chapter(106))
        result = self.merge()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.generated()[0].name, 'merged-105-106.md')

    def test_partial_archive_can_begin_above_one(self):
        self.put('105.md', chapter(105))
        self.put('106.md', chapter(106))
        result = self.merge('--archive')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('第105章', (self.text / 'vol-002.md').read_text(encoding='utf-8'))

    def test_cross_volume_gap_fails(self):
        self.put('vol-001.md', chapter(99))
        self.put('vol-002.md', chapter(101))
        self.assertNotEqual(self.merge().returncode, 0)
        self.assertEqual(self.generated(), [])

    def test_multiple_chapters_in_loose_file_fail(self):
        self.put('001.md', chapter(1) + chapter(2))
        self.assertNotEqual(self.merge().returncode, 0)

    def test_numeric_excerpt_is_ignored(self):
        self.put('001.md', chapter(1))
        self.put('001-excerpt.md', chapter(2))
        result = self.merge()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.generated()[0].name, 'merged-1-1.md')

    def test_archive_new_gap_leaves_all_sources_unchanged(self):
        source = self.put('001.md', chapter(1))
        other = self.put('003.md', chapter(3))
        before = (source.read_bytes(), other.read_bytes())
        self.assertNotEqual(self.merge('--archive').returncode, 0)
        self.assertFalse((self.text / 'vol-001.md').exists())
        self.assertEqual((source.read_bytes(), other.read_bytes()), before)

    def test_archive_append_across_volume_boundary(self):
        old = self.put('vol-001.md', chapter(99) + chapter(100))
        source = self.put('101.md', chapter(101))
        before = old.read_bytes()
        result = self.merge('--archive')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(old.read_bytes(), before)
        self.assertTrue(source.exists())
        self.assertIn('第101章', (self.text / 'vol-002.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
