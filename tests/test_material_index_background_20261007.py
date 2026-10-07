"""Worker completion indexes cloud-stored materials off the request thread."""
import threading
import unittest
from unittest.mock import patch

from teacher_app.worker import routes as worker_routes


class MaterialIndexBackgroundTests(unittest.TestCase):
    def _run_and_wait(self, material_id, **patches):
        done = threading.Event()
        before = {t for t in threading.enumerate()}

        def finished(*_args, **_kwargs):
            try:
                if "side_effect" in patches:
                    raise patches["side_effect"]
            finally:
                done.set()

        with patch.object(worker_routes, "auto_index_material", side_effect=finished) as hook:
            worker_routes._index_material_in_background(object(), material_id)
            started = [t for t in threading.enumerate() if t not in before]
            self.assertTrue(done.wait(5), "background indexing never ran")
            for thread in started:
                thread.join(5)
        return hook

    def test_indexing_runs_in_a_background_daemon_thread(self):
        caller = threading.get_ident()
        seen = {}
        done = threading.Event()

        def hook(app, material_id):
            seen["thread"] = threading.get_ident()
            seen["daemon"] = threading.current_thread().daemon
            seen["id"] = material_id
            done.set()

        with patch.object(worker_routes, "auto_index_material", side_effect=hook):
            worker_routes._index_material_in_background(object(), "mat-1")
            self.assertTrue(done.wait(5))
        self.assertNotEqual(seen["thread"], caller, "must not index inside the Worker request")
        self.assertTrue(seen["daemon"], "a stuck download must never block shutdown")
        self.assertEqual(seen["id"], "mat-1")

    def test_a_failing_index_never_raises_into_the_worker_request(self):
        hook = self._run_and_wait("mat-2", side_effect=RuntimeError("mega is down"))
        self.assertEqual(hook.call_count, 1)

    def test_blank_material_id_starts_nothing(self):
        before = threading.active_count()
        with patch.object(worker_routes, "auto_index_material") as hook:
            worker_routes._index_material_in_background(object(), "")
        self.assertEqual(hook.call_count, 0)
        self.assertEqual(threading.active_count(), before)

    def test_only_one_material_is_indexed_at_a_time(self):
        active = {"now": 0, "max": 0}
        guard = threading.Lock()
        finished = threading.Semaphore(0)

        def hook(app, material_id):
            with guard:
                active["now"] += 1
                active["max"] = max(active["max"], active["now"])
            threading.Event().wait(0.05)
            with guard:
                active["now"] -= 1
            finished.release()

        with patch.object(worker_routes, "auto_index_material", side_effect=hook):
            for number in range(4):
                worker_routes._index_material_in_background(object(), f"mat-{number}")
            for _ in range(4):
                self.assertTrue(finished.acquire(timeout=5))
        self.assertEqual(active["max"], 1)


if __name__ == "__main__":
    unittest.main()
