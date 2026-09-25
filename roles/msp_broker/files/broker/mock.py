import json
import os
import subprocess
import tempfile
import time

from .adapters import Adapter, AdapterError, ExecResult, clamp, sanitize


class MockAdapter(Adapter):
    name = "mock"
    reads = ("state",)

    def __init__(self, paths):
        self.path = os.path.join(paths.state, "mock_state.json")
        self.rundir = os.path.join(paths.state, "run")

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {"counter": 0, "last_message": "", "last_target": ""}

    def _save(self, state):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp.%d" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, sort_keys=True)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    def read(self, client, verb, args):
        state = self._load()
        if verb == "state":
            return {
                "source": "mock_adapter",
                "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "state": state,
            }
        raise AdapterError("unknown read verb: %s" % verb)

    def precheck(self, operation, target, parameters):
        return {"counter": self._load()["counter"], "target": target["id"]}

    def preconditions_hold(self, stored, fresh):
        return stored.get("counter") == fresh.get("counter")

    def execute(self, operation, target, parameters, plan, script_path=None):
        before = self._load()
        if operation == "mock.fail":
            return ExecResult(rc=1, stderr="deliberate failure\n", pre_state=before, post_state=before)
        if operation == "mock.sleep":
            time.sleep(parameters.get("seconds", 1))
        after = dict(before)
        after["counter"] = before.get("counter", 0) + 1
        after["last_target"] = target["id"]
        if operation == "mock.echo":
            after["last_message"] = parameters.get("message", "")
        self._save(after)
        return ExecResult(
            rc=0,
            stdout="mock %s ok\n" % operation,
            pre_state=before,
            post_state=after,
        )

    def run_script(self, interpreter, script_path, timeout_seconds):
        if not os.path.isfile(script_path):
            raise AdapterError("frozen script is missing")
        os.makedirs(self.rundir, mode=0o700, exist_ok=True)
        workdir = tempfile.mkdtemp(prefix="script-", dir=self.rundir)
        try:
            proc = subprocess.run(
                [interpreter, script_path],
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                env={"PATH": "/usr/bin:/bin", "HOME": workdir, "LANG": "C"},
            )
            return ExecResult(
                rc=proc.returncode,
                stdout=clamp(proc.stdout),
                stderr=clamp(proc.stderr),
                transcript=sanitize(proc.stdout + proc.stderr),
            )
        except subprocess.TimeoutExpired as exc:
            return ExecResult(
                rc=124,
                stdout=clamp((exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")),
                stderr="timed out after %ss\n" % timeout_seconds,
                transcript="timed out after %ss" % timeout_seconds,
            )
        finally:
            try:
                os.rmdir(workdir)
            except OSError:
                pass
