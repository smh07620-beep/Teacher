import unittest
from pathlib import Path


ROOT=Path(__file__).parents[1]


class F2LearnerNextActionUiTests(unittest.TestCase):
    def test_command_center_renders_one_explicit_next_action(self):
        source=ROOT.joinpath('static','training-command-center-71.js').read_text(encoding='utf-8')
        self.assertIn('training-command-next-71',source)
        self.assertIn('command?.nextAction',source)
        self.assertIn('data-learner-next-action',source)
        self.assertIn("if (item?.materialId) query.set('materialId'",source)

    def test_home_todo_marks_the_same_canonical_next_action(self):
        source=ROOT.joinpath('static','learner-todo-convergence-1025.js').read_text(encoding='utf-8')
        self.assertIn('command?.nextAction',source)
        self.assertIn('data-learner-next-action',source)
        self.assertIn("if(item?.materialId)query.set('materialId'",source)


if __name__=='__main__':
    unittest.main()
