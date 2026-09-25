"""Unit tests for the TODOs-style Kanban Board UI assets and responses."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class KanbanBoardTests(unittest.TestCase):
    def test_ui_html_contains_kanban_styles_and_nav(self):
        content = (ROOT / 'ui.html').read_text(encoding='utf-8')
        self.assertIn('kanban-grid', content)
        self.assertIn('kanban-col', content)
        self.assertIn('data-view="board"', content)
        self.assertIn('Kanban Board', content)

    def test_ui_zh_contains_kanban_styles_and_nav(self):
        content = (ROOT / 'ui.zh-CN.html').read_text(encoding='utf-8')
        self.assertIn('kanban-grid', content)
        self.assertIn('kanban-col', content)
        self.assertIn('data-view="board"', content)
        self.assertIn('任务看板', content)

    def test_ui_js_defines_kanban_columns_and_render_board(self):
        js = (ROOT / 'ui.js').read_text(encoding='utf-8')
        self.assertIn('colTodo', js)
        self.assertIn('colRunning', js)
        self.assertIn('colNeedsInput', js)
        self.assertIn('colReview', js)
        self.assertIn('colDone', js)
        self.assertIn('renderBoard', js)
        self.assertIn("current = 'board'", js)
        self.assertIn('new-task-dialog', js)
        self.assertIn('detail-modal', js)


if __name__ == '__main__':
    unittest.main()
