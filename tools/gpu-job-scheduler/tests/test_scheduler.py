import subprocess
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCHEDULER = Path(__file__).parents[1] / "gpu_job_scheduler.py"


class SchedulerTests(unittest.TestCase):
    def test_serializes_mocked_jobs_across_processes(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "lock"
            marker = Path(temp) / "started"
            first_code = (
                "import pathlib,time; p=pathlib.Path(r'%s'); "
                "p.write_text('first'); time.sleep(.5)" % marker
            )
            second_code = (
                "import pathlib,time; p=pathlib.Path(r'%s'); "
                "assert p.read_text() == 'first'; p.write_text('second')" % marker
            )
            child = "import sys; sys.path.insert(0, r'%s'); import gpu_job_scheduler as s; " % SCHEDULER.parent
            first = subprocess.Popen([sys.executable, "-c", child + "raise SystemExit(s.run(%r, 2, %r))" %
                                      ([sys.executable, "-c", first_code], str(lock))])
            time.sleep(.08)
            second = subprocess.Popen([sys.executable, "-c", child + "raise SystemExit(s.run(%r, 2, %r))" %
                                       ([sys.executable, "-c", second_code], str(lock))])
            self.assertEqual(first.wait(timeout=3), 0)
            self.assertEqual(second.wait(timeout=3), 0)
            self.assertEqual(marker.read_text(), "second")

    def test_holds_lock_through_client_poll_and_download_lifecycle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lock = root / "lock"
            marker = root / "state"
            # Model an async client: submit, poll repeatedly, then download.
            client = ("import pathlib,time; p=pathlib.Path(r'%s'); "
                      "p.write_text('submitted'); time.sleep(.12); "
                      "p.write_text('polling'); time.sleep(.12); "
                      "assert p.read_text() == 'polling'; p.write_text('downloaded')") % marker
            observer = ("import pathlib; p=pathlib.Path(r'%s'); "
                        "assert p.read_text() == 'downloaded'; p.write_text('done')") % marker
            module = "import sys; sys.path.insert(0, r'%s'); import gpu_job_scheduler as s; " % SCHEDULER.parent
            first = subprocess.Popen([sys.executable, "-c", module + "raise SystemExit(s.run(%r, 2, %r))" %
                                     ([sys.executable, "-c", client], str(lock))])
            time.sleep(.04)
            second = subprocess.Popen([sys.executable, "-c", module + "raise SystemExit(s.run(%r, 2, %r))" %
                                       ([sys.executable, "-c", observer], str(lock))])
            self.assertEqual(first.wait(timeout=4), 0)
            self.assertEqual(second.wait(timeout=4), 0)
            self.assertEqual(marker.read_text(), "done")

    def test_returns_child_exit_code(self):
        with tempfile.TemporaryDirectory() as temp:
            module = "import sys; sys.path.insert(0, r'%s'); import gpu_job_scheduler as s; " % SCHEDULER.parent
            result = subprocess.run([sys.executable, "-c", module +
                                     "raise SystemExit(s.run([%r, '-c', 'raise SystemExit(37)'], 1, %r))" %
                                     (sys.executable, str(Path(temp) / "lock"))])
            self.assertEqual(result.returncode, 37)

    def test_command_timeout_kills_group_and_releases_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "lock"
            env = {**os.environ, "HOME": temp}
            result = subprocess.run([sys.executable, str(SCHEDULER), "--command-timeout", ".1",
                                     "--wait-timeout", "1", "--", sys.executable, "-c",
                                     "import time; time.sleep(30)"], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 124)
            self.assertIn("command timed out", result.stderr)
            self.assertEqual(subprocess.run([sys.executable, str(SCHEDULER), "--wait-timeout", "1", "--", "true"],
                                            env=env).returncode, 0)

    def test_interrupt_terminates_child_group_and_releases_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "lock"
            pidfile = Path(temp) / "descendant"
            terminated = Path(temp) / "descendant-terminated"
            descendant_code = ("import os,time,pathlib,signal; "
                               "signal.signal(signal.SIGTERM, lambda *_: pathlib.Path(r'%s').write_text('yes')); "
                               "pathlib.Path(r'%s').write_text(str(os.getpid())); time.sleep(30)") % (terminated, pidfile)
            parent_code = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',%r]); time.sleep(30)" % descendant_code
            env = {**os.environ, "HOME": temp}
            owner = subprocess.Popen([sys.executable, str(SCHEDULER), "--wait-timeout", "2", "--",
                                      sys.executable, "-c", parent_code], env=env)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and not pidfile.exists():
                time.sleep(.01)
            self.assertTrue(pidfile.exists())
            descendant = int(pidfile.read_text())
            owner.send_signal(__import__('signal').SIGINT)
            self.assertEqual(owner.wait(timeout=4), 130)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and not terminated.exists():
                time.sleep(.02)
            self.assertTrue(terminated.exists(), f"descendant {descendant} did not receive termination")
            self.assertEqual(subprocess.run([sys.executable, str(SCHEDULER), "--wait-timeout", "1", "--", "true"],
                                            env=env).returncode, 0)

    def test_repeated_signals_do_not_interrupt_process_group_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "lock"
            pidfile = Path(temp) / "ignoring-descendant"
            # Parent client starts a grandchild that ignores TERM, forcing the
            # scheduler to remain in cleanup until the grace period expires.
            owner_code = ("import sys,subprocess,time; subprocess.Popen([sys.executable,'-c',%r]); time.sleep(30)") % (
                "import signal,time,pathlib,os; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "pathlib.Path(r'%s').write_text(str(os.getpid())); time.sleep(30)" % pidfile
            )
            # The inline scheduler executes a client that starts the descendant.
            scheduler_code = ("import sys,subprocess,time,signal,pathlib; "
                              "sys.path.insert(0, r'%s'); import gpu_job_scheduler as s; s.TERMINATE_GRACE=.7; "
                              "client=%r\n"
                              "try:\n s.run([sys.executable,'-c',client], 2, r'%s')\n"
                              "except s.CommandInterrupted as e: raise SystemExit(128+e.signum)") % (
                                  SCHEDULER.parent, owner_code, lock
                              )
            owner = subprocess.Popen([sys.executable, "-c", scheduler_code])
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and not pidfile.exists():
                time.sleep(.01)
            self.assertTrue(pidfile.exists())
            descendant = int(pidfile.read_text())
            owner.send_signal(__import__('signal').SIGINT)
            time.sleep(.08)
            owner.send_signal(__import__('signal').SIGTERM)
            time.sleep(.08)
            owner.send_signal(__import__('signal').SIGINT)
            self.assertEqual(owner.wait(timeout=4), 130)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                try:
                    os.kill(descendant, 0)
                except ProcessLookupError:
                    break
                time.sleep(.02)
            with self.assertRaises(ProcessLookupError):
                os.kill(descendant, 0)
            module = "import sys; sys.path.insert(0, r'%s'); import gpu_job_scheduler as s; " % SCHEDULER.parent
            self.assertEqual(subprocess.run([sys.executable, "-c", module + "s.run(['true'],1,r'%s')" % lock]).returncode, 0)

    def test_guardian_failure_drains_job_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "lock"
            started = Path(temp) / "started"
            terminated = Path(temp) / "terminated"
            guardian_code = ("import pathlib,time\n"
                             "p=pathlib.Path(r'%s')\n"
                             "deadline=time.monotonic()+3\n"
                             "while not p.exists() and time.monotonic()<deadline: time.sleep(.01)\n"
                             "time.sleep(.05)") % started
            command_code = ("import pathlib,time,signal,sys; "
                            "signal.signal(signal.SIGTERM, lambda *_: (pathlib.Path(r'%s').write_text('yes'), sys.exit(0))); "
                            "pathlib.Path(r'%s').write_text('yes'); time.sleep(30)") % (terminated, started)
            driver = ("import subprocess,sys\n"
                      "sys.path.insert(0,r'%s')\n"
                      "import gpu_job_scheduler as s\n"
                      "s._start_guardian=lambda pgid,fd: subprocess.Popen([sys.executable,'-c',%r])\n"
                      "try:\n s.run([sys.executable,'-c',%r],2,r'%s')\n"
                      "except RuntimeError as e: print(e); raise SystemExit(2)") % (
                          SCHEDULER.parent, guardian_code, command_code, lock
                      )
            result = subprocess.run([sys.executable, "-c", driver], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("guardian exited unexpectedly", result.stdout)
            self.assertTrue(terminated.exists())
            module = "import sys; sys.path.insert(0, r'%s'); import gpu_job_scheduler as s; " % SCHEDULER.parent
            released = subprocess.run([sys.executable, "-c", module + "s.run(['true'],1,r'%s')" % lock])
            self.assertEqual(released.returncode, 0)

    def test_sigkill_owner_keeps_lock_until_client_exits(self):
        with tempfile.TemporaryDirectory() as temp:
            env = {**os.environ, "HOME": temp}
            root = Path(temp)
            started = root / "started"
            done = root / "done"
            client = ("import pathlib,time,signal; "
                      "signal.signal(signal.SIGTERM, lambda *_: pathlib.Path(r'%s').write_text('done')); "
                      "pathlib.Path(r'%s').write_text('started'); time.sleep(30)") % (done, started)
            owner = subprocess.Popen([sys.executable, str(SCHEDULER), "--wait-timeout", "2", "--",
                                      sys.executable, "-c", client], env=env)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and not started.exists():
                time.sleep(.01)
            self.assertTrue(started.exists())
            owner.kill()
            owner.wait(timeout=2)
            observer = ("import pathlib; assert pathlib.Path(r'%s').read_text() == 'done'") % done
            result = subprocess.run([sys.executable, str(SCHEDULER), "--wait-timeout", "2", "--",
                                     sys.executable, "-c", observer], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_sigkill_owner_guardian_drains_close_on_exec_grandchild(self):
        with tempfile.TemporaryDirectory() as temp:
            env = {**os.environ, "HOME": temp}
            root = Path(temp)
            started = root / "grandchild-started"
            descendant_terminated = root / "grandchild-terminated"
            grandchild = ("import pathlib,time,signal; "
                          "signal.signal(signal.SIGTERM, lambda *_: pathlib.Path(r'%s').write_text('yes')); "
                          "pathlib.Path(r'%s').write_text('started'); time.sleep(30)") % (descendant_terminated, started)
            client = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',%r]); time.sleep(30)" % grandchild
            owner = subprocess.Popen([sys.executable, str(SCHEDULER), "--wait-timeout", "2", "--",
                                      sys.executable, "-c", client], env=env)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and not started.exists():
                time.sleep(.01)
            self.assertTrue(started.exists())
            owner.kill()
            owner.wait(timeout=2)
            observer = "import pathlib; assert pathlib.Path(r'%s').exists()" % descendant_terminated
            result = subprocess.run([sys.executable, str(SCHEDULER), "--wait-timeout", "2", "--",
                                     sys.executable, "-c", observer], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(descendant_terminated.exists())

    def test_timeout_reports_contention(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "lock"
            import fcntl
            with lock.open("w+") as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                code = "import sys; sys.path.insert(0, r'%s'); import gpu_job_scheduler as s; s.run(['true'], .05, r'%s')" % (SCHEDULER.parent, lock)
                result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("timed out", result.stderr)
                fcntl.flock(held, fcntl.LOCK_UN)

    def test_crashed_owner_releases_kernel_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "lock"
            module = "import sys; sys.path.insert(0, r'%s'); import gpu_job_scheduler as s; " % SCHEDULER.parent
            owner = subprocess.Popen([sys.executable, "-c", module + "s.run([%r, '-c', 'import time; time.sleep(.2)'], 2, %r)" % (sys.executable, str(lock))])
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not lock.exists():
                time.sleep(.01)
            time.sleep(.05)
            owner.kill()
            owner.wait(timeout=2)
            # The child inherited the lock descriptor and completes before the
            # next acquisition is attempted.
            time.sleep(.3)
            command = module + "s.run(['true'], 1, %r)" % str(lock)
            self.assertEqual(subprocess.run([sys.executable, "-c", command]).returncode, 0)


if __name__ == "__main__":
    unittest.main()
