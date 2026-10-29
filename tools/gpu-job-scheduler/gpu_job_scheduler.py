#!/usr/bin/env python3
"""Serialize GPU-heavy jobs across local processes using an advisory file lock."""
from __future__ import annotations

import argparse
import fcntl
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

LOCK_PATH = Path.home() / "AIStudio/tools/.gpu-job-scheduler.lock"
DEFAULT_WAIT_TIMEOUT = 3600.0
POLL_INTERVAL = 0.25
COMMAND_POLL_INTERVAL = 0.1
TERMINATE_GRACE = 1.0
GUARDIAN_POLL_INTERVAL = 0.05


class CommandTimeout(TimeoutError):
    pass


class CommandInterrupted(Exception):
    def __init__(self, signum: int):
        self.signum = signum


def _group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _stop_process_group(pgid: int, child: subprocess.Popen[bytes]) -> None:
    """Stop all descendants that remain in the command's process group."""
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + TERMINATE_GRACE
    while time.monotonic() < deadline and _group_exists(pgid):
        try:
            child.wait(timeout=min(COMMAND_POLL_INTERVAL, max(0, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            pass
        time.sleep(COMMAND_POLL_INTERVAL)
    if _group_exists(pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        child.wait(timeout=TERMINATE_GRACE)
    except subprocess.TimeoutExpired:
        pass


def _drain_process_group(pgid: int) -> None:
    """Terminate a process group without needing to be its parent."""
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + TERMINATE_GRACE
    while time.monotonic() < deadline and _group_exists(pgid):
        time.sleep(GUARDIAN_POLL_INTERVAL)
    if _group_exists(pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _guardian_main(owner_pid: int, pgid: int) -> int:
    """Keep the lock and drain the command group if its scheduler is killed."""
    while os.getppid() == owner_pid:
        time.sleep(GUARDIAN_POLL_INTERVAL)
    _drain_process_group(pgid)
    return 0


def _start_guardian(pgid: int, lock_fd: int) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--_guardian",
         str(os.getpid()), str(pgid)],
        start_new_session=True,
        pass_fds=(lock_fd,),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop_guardian(guardian: subprocess.Popen[bytes] | None) -> None:
    if guardian is None:
        return
    if guardian.poll() is None:
        guardian.terminate()
    try:
        guardian.wait(timeout=TERMINATE_GRACE)
    except subprocess.TimeoutExpired:
        guardian.kill()
        guardian.wait(timeout=TERMINATE_GRACE)


def _cleanup_job(pgid: int | None, child: subprocess.Popen[bytes] | None,
                 guardian: subprocess.Popen[bytes] | None) -> None:
    """Finish cleanup without repeated terminal/termination signals interrupting it."""
    old_handlers: dict[int, object] = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        old_handlers[signum] = signal.signal(signum, signal.SIG_IGN)
    try:
        try:
            if pgid is not None and child is not None:
                _stop_process_group(pgid, child)
        finally:
            _stop_guardian(guardian)
    finally:
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)


def run(command: list[str], timeout: float, lock_path: Path = LOCK_PATH,
        command_timeout: float | None = None) -> int:
    if not command:
        raise ValueError("a command is required after --")
    if timeout < 0:
        raise ValueError("wait timeout must be non-negative")
    if command_timeout is not None and command_timeout < 0:
        raise ValueError("command timeout must be non-negative")
    lock_path = Path(lock_path).expanduser()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_file = lock_path.open("a+")
    except OSError as exc:
        raise RuntimeError(f"cannot open GPU scheduler lock {lock_path}: {exc}") from exc
    with lock_file:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    lock_file.seek(0)
                    owner = lock_file.read().strip() or "unknown process"
                    raise TimeoutError(
                        f"timed out after {timeout:g}s waiting for GPU generation lock "
                        f"({owner}); increase --wait-timeout or wait for that job"
                    )
                time.sleep(min(POLL_INTERVAL, remaining))
            except OSError as exc:
                raise RuntimeError(f"failed acquiring GPU scheduler lock: {exc}") from exc
        try:
            lock_file.seek(0)
            lock_file.truncate()
            lock_file.write(f"pid={os.getpid()} started={int(time.time())}\n")
            lock_file.flush()
            child: subprocess.Popen[bytes] | None = None
            guardian: subprocess.Popen[bytes] | None = None
            old_handlers: dict[int, object] = {}
            try:
                def interrupted(signum: int, _frame: object) -> None:
                    raise CommandInterrupted(signum)

                for signum in (signal.SIGINT, signal.SIGTERM):
                    old_handlers[signum] = signal.signal(signum, interrupted)
                # Keeping the lock descriptor in the command protects against
                # a scheduler crash while that command remains alive. Descendants
                # retain it only if their launcher passes the descriptor through.
                child = subprocess.Popen(command, start_new_session=True,
                                         pass_fds=(lock_file.fileno(),))
                pgid = child.pid
                # The guardian has its own session and retains the lock FD. Once
                # started, it drains the job group after scheduler death,
                # including close-on-exec grandchildren. The direct child owns
                # the lock during the short interval before guardian startup.
                guardian = _start_guardian(pgid, lock_file.fileno())
                deadline = (None if command_timeout is None
                            else time.monotonic() + command_timeout)
                while True:
                    if guardian.poll() is not None:
                        _cleanup_job(pgid, child, guardian)
                        guardian = None
                        raise RuntimeError(
                            "GPU scheduler guardian exited unexpectedly; "
                            "the scheduled process group was terminated"
                        )
                    wait = COMMAND_POLL_INTERVAL
                    if deadline is not None:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise CommandTimeout(
                                f"scheduled command timed out after {command_timeout:g}s"
                            )
                        wait = min(wait, remaining)
                    try:
                        code = child.wait(timeout=wait)
                    except subprocess.TimeoutExpired:
                        continue
                    if guardian.poll() is not None:
                        _cleanup_job(pgid, child, guardian)
                        guardian = None
                        raise RuntimeError(
                            "GPU scheduler guardian exited unexpectedly; "
                            "the scheduled process group was terminated"
                        )
                    # A client can exit while a GPU worker it launched is still
                    # running. Drain the entire group before releasing the lock.
                    _cleanup_job(pgid, child, guardian)
                    guardian = None
                    return code
            except (CommandTimeout, CommandInterrupted):
                _cleanup_job(child.pid if child is not None else None, child, guardian)
                guardian = None
                raise
            except OSError as exc:
                _cleanup_job(child.pid if child is not None else None, child, guardian)
                guardian = None
                raise RuntimeError(f"could not start scheduled command {command[0]!r}: {exc}") from exc
            finally:
                if guardian is not None:
                    _cleanup_job(child.pid if child is not None else None, child, guardian)
                for signum, handler in old_handlers.items():
                    signal.signal(signum, handler)
        finally:
            # flock is released by the kernel on normal exit or process death.
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait-timeout", type=float, default=DEFAULT_WAIT_TIMEOUT,
                        help="maximum seconds to wait for another GPU job (default: 3600)")
    parser.add_argument("--command-timeout", type=float, default=None,
                        help="maximum seconds to allow the scheduled command to run")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="command and arguments, preceded by --")
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        return run(command, args.wait_timeout, command_timeout=args.command_timeout)
    except CommandInterrupted as exc:
        return 128 + exc.signum
    except CommandTimeout as exc:
        print(f"gpu-job-scheduler: {exc}", file=sys.stderr)
        return 124
    except (ValueError, RuntimeError, TimeoutError) as exc:
        print(f"gpu-job-scheduler: {exc}", file=sys.stderr)
        return 75 if isinstance(exc, TimeoutError) else 2


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--_guardian":
        raise SystemExit(_guardian_main(int(sys.argv[2]), int(sys.argv[3])))
    raise SystemExit(main())
