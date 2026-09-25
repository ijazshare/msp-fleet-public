import fcntl
import hashlib
import json
import logging
import os
import stat
import uuid
from datetime import datetime, timedelta, timezone

from . import model, scriptcheck
from .adapters import AdapterError, ExecResult, Refused, clamp, sanitize
from .model import PlanError

LOG = logging.getLogger("msp-broker")


def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


class BrokerService:
    def __init__(self, paths, policy, client, store, adapters, clock=utcnow):
        self.paths = paths
        self.policy = policy
        self.client = client
        self.store = store
        self.adapters = adapters
        self.clock = clock

    def _now(self):
        return self.clock()

    def _expire(self):
        self.store.expire_stale(self._now())

    def _require_read(self, actor):
        if not actor.can_read:
            raise Refused("not permitted")

    def _require_approve(self, actor):
        if not actor.can_approve:
            raise Refused("not an approver")

    def _log(self, event, **fields):
        try:
            os.makedirs(self.paths.log, exist_ok=True)
            line = json.dumps({"ts": self._now(), "event": event, **fields}, sort_keys=True)
            fd = os.open(self.paths.log + "/broker.log", os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                os.write(fd, (line + "\n").encode("utf-8"))
            finally:
                os.close(fd)
        except OSError:
            LOG.warning("cannot write broker log")

    def _adapter(self, name):
        adapter = self.adapters.get(name)
        if adapter is None:
            raise Refused("adapter is not available: %s" % name)
        return adapter

    def _allowed(self, adapter_name, operation_name):
        cfg = self.policy["adapters"].get(adapter_name)
        if not cfg or not cfg.get("enabled"):
            raise Refused("adapter is not enabled: %s" % adapter_name)
        if operation_name not in cfg["operations"]:
            raise Refused("unsupported operation: %s" % operation_name)

    def resolve_target(self, target_ref):
        if not isinstance(target_ref, str) or not target_ref:
            raise Refused("target is required")
        target = self.store.inventory_get(target_ref)
        if target is None:
            matches = self.store.inventory_by_name(target_ref)
            if len(matches) > 1:
                raise Refused("target is ambiguous: %s" % target_ref)
            target = matches[0] if matches else None
        if target is None:
            raise Refused("unknown target: %s" % target_ref)
        if target["client_id"] != self.client["client_id"]:
            raise Refused("target belongs to another client")
        return target

    def _validated_operation(self, operation_name, target_ref, parameters):
        op = model.get_operation(operation_name)
        if op is None:
            raise Refused("unknown operation: %s" % operation_name)
        if op.risk == "FORBIDDEN":
            raise Refused("operation is forbidden: %s" % operation_name)
        self._allowed(op.adapter, op.name)
        target = self.resolve_target(target_ref)
        if target["adapter"] != op.adapter:
            raise Refused("target is not handled by adapter %s" % op.adapter)
        if target["kind"] not in op.target_kinds:
            raise Refused("operation %s does not apply to %s" % (op.name, target["kind"]))
        try:
            clean = model.validate_params(op, parameters)
        except PlanError as exc:
            raise Refused(str(exc))
        return op, target, clean

    def _timeout_for(self, risk):
        return 600

    def propose(self, actor, operation_name, target_ref, parameters):
        self._require_read(actor)
        self._expire()
        op, target, clean = self._validated_operation(operation_name, target_ref, parameters)
        adapter = self._adapter(op.adapter)
        try:
            pre_state = adapter.precheck(op.name, target, clean)
        except AdapterError as exc:
            raise Refused(str(exc))
        plan = model.build_plan(
            self.client, op.adapter, op.name, target, clean, op.executor,
            self._timeout_for(op.risk), pre_state,
        )
        proposal_id = str(uuid.uuid4())
        created = self._now()
        expires = (parse_time(created) + timedelta(seconds=self.policy["approval_ttl_seconds"]))
        confirmation = model.confirmation_phrase(op, target["name"]) if op.risk == "HIGH" else ""
        self.store.insert_proposal({
            "proposal_id": proposal_id,
            "client_id": self.client["client_id"],
            "site_id": self.client["site_id"],
            "request_uid": actor.uid,
            "adapter": op.adapter,
            "operation": op.name,
            "target_id": target["id"],
            "target_name": target["name"],
            "parameters": clean,
            "risk": op.risk,
            "status": "PROPOSED",
            "plan": plan,
            "execution_hash": model.plan_hash(plan),
            "confirmation": confirmation,
            "created_at": created,
            "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "pre_state": pre_state,
        })
        self._log("proposed", proposal_id=proposal_id, operation=op.name, target=target["id"],
                  risk=op.risk, uid=actor.uid)
        return self._summary(self.store.get(proposal_id), include_confirmation=True)

    def propose_script(self, actor, target_ref, interpreter, file_path, purpose, effects, timeout_seconds=None):
        self._require_read(actor)
        self._expire()
        cfg = self.policy.get("script", {})
        if not cfg.get("enabled"):
            raise Refused("script proposals are not enabled")
        target = self.resolve_target(target_ref)
        adapter = self._adapter(target["adapter"])
        if not hasattr(adapter, "run_script"):
            raise Refused("adapter %s cannot run scripts" % target["adapter"])
        if interpreter not in cfg.get("interpreters", []):
            raise Refused("interpreter is not allowed: %s" % interpreter)
        timeout = timeout_seconds if timeout_seconds is not None else cfg["default_timeout_seconds"]
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= cfg["max_timeout_seconds"]:
            raise Refused("timeout must be an integer 1..%d" % cfg["max_timeout_seconds"])
        if not isinstance(purpose, str) or not purpose.strip():
            raise Refused("purpose is required")
        if len(purpose) > 512 or len(effects or "") > 2048:
            raise Refused("declared text is too long")
        try:
            fd = os.open(file_path, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as exc:
            raise Refused("cannot open script: %s" % exc)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise Refused("script must be a regular file")
            if st.st_size > cfg["max_bytes"]:
                raise Refused("script exceeds %d bytes" % cfg["max_bytes"])
            if actor.uid != 0 and st.st_uid != actor.uid:
                raise Refused("script must be owned by the requester")
            data = os.read(fd, cfg["max_bytes"] + 1)
        finally:
            os.close(fd)
        text = data.decode("utf-8", errors="replace")
        findings = scriptcheck.scan(text, cfg.get("forbidden_patterns", []))
        if any(f["severity"] == "FORBIDDEN" for f in findings):
            raise Refused("script contains a forbidden pattern")
        proposal_id = str(uuid.uuid4())
        proposal_dir = os.path.join(self.paths.proposals, proposal_id)
        os.makedirs(proposal_dir, mode=0o700, exist_ok=True)
        script_path = os.path.join(proposal_dir, "script")
        with open(script_path, "wb") as fh:
            fh.write(data)
        os.chmod(script_path, 0o600)
        digest = hashlib.sha256(data).hexdigest()
        pre_state = {}
        try:
            pre_state = adapter.precheck("script.run", target, {})
        except AdapterError:
            pre_state = {}
        script = {
            "sha256": digest,
            "bytes": len(data),
            "interpreter": interpreter,
            "timeout_seconds": timeout,
            "findings": findings,
            "path": script_path,
        }
        ai_declared = {"purpose": purpose.strip(), "effects": (effects or "").strip()}
        plan = model.build_plan(
            self.client, target["adapter"], "script.run", target, {}, "run_script", timeout,
            pre_state, script=script, ai_declared=ai_declared,
        )
        created = self._now()
        expires = parse_time(created) + timedelta(seconds=self.policy["approval_ttl_seconds"])
        self.store.insert_proposal({
            "proposal_id": proposal_id,
            "client_id": self.client["client_id"],
            "site_id": self.client["site_id"],
            "request_uid": actor.uid,
            "adapter": target["adapter"],
            "operation": "script.run",
            "target_id": target["id"],
            "target_name": target["name"],
            "parameters": {},
            "risk": "HIGH",
            "status": "PROPOSED",
            "plan": plan,
            "execution_hash": model.plan_hash(plan),
            "confirmation": "APPROVE %s" % target["name"],
            "created_at": created,
            "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "pre_state": pre_state,
            "ai_declared": ai_declared,
        })
        self._log("proposed_script", proposal_id=proposal_id, target=target["id"], sha256=digest, uid=actor.uid)
        return self._summary(self.store.get(proposal_id), include_confirmation=True)

    def propose_plan(self, actor, steps, purpose):
        self._require_read(actor)
        self._expire()
        cfg = self.policy.get("plans", {})
        if not cfg.get("enabled"):
            raise Refused("plan proposals are not enabled")
        if not isinstance(steps, list) or not steps or len(steps) > cfg["max_steps"]:
            raise Refused("plan must contain 1..%d steps" % cfg["max_steps"])
        if not isinstance(purpose, str) or not purpose.strip() or len(purpose) > 512:
            raise Refused("purpose is required")
        frozen = []
        risk = "LOW"
        for step in steps:
            if not isinstance(step, dict):
                raise Refused("each step must be an object")
            op, target, clean = self._validated_operation(
                step.get("operation"), step.get("target"), step.get("parameters", {})
            )
            if model.RISK_ORDER[op.risk] > model.RISK_ORDER[risk]:
                risk = op.risk
            frozen.append({
                "adapter": op.adapter,
                "operation": op.name,
                "target_id": target["id"],
                "target_name": target["name"],
                "target_external_id": target["external_id"],
                "parameters": clean,
                "executor": op.executor,
            })
        first_target = self.resolve_target(frozen[0]["target_id"])
        plan = model.build_plan(
            self.client, first_target["adapter"], "plan.run", first_target, {}, "run_plan",
            600, {}, steps=frozen, ai_declared={"purpose": purpose.strip()},
        )
        proposal_id = str(uuid.uuid4())
        created = self._now()
        expires = parse_time(created) + timedelta(seconds=self.policy["approval_ttl_seconds"])
        confirmation = "APPROVE PLAN %s" % first_target["name"] if risk == "HIGH" else ""
        self.store.insert_proposal({
            "proposal_id": proposal_id,
            "client_id": self.client["client_id"],
            "site_id": self.client["site_id"],
            "request_uid": actor.uid,
            "adapter": first_target["adapter"],
            "operation": "plan.run",
            "target_id": first_target["id"],
            "target_name": first_target["name"],
            "parameters": {},
            "risk": risk,
            "status": "PROPOSED",
            "plan": plan,
            "execution_hash": model.plan_hash(plan),
            "confirmation": confirmation,
            "created_at": created,
            "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "pre_state": {},
            "ai_declared": {"purpose": purpose.strip()},
        })
        self._log("proposed_plan", proposal_id=proposal_id, steps=len(frozen), risk=risk, uid=actor.uid)
        return self._summary(self.store.get(proposal_id), include_confirmation=True)

    def read(self, actor, verb, args):
        self._require_read(actor)
        self._expire()
        if verb == "inventory":
            return {
                "source": "broker_inventory",
                "observed_at": self._now(),
                "targets": [
                    {k: t[k] for k in ("id", "kind", "name", "adapter", "external_id")}
                    for t in self.store.inventory_list()
                    if t["client_id"] == self.client["client_id"]
                ],
            }
        if verb == "target":
            target = self.resolve_target(args[0] if args else "")
            return {"source": "broker_inventory", "observed_at": self._now(), "target": target}
        if verb == "proposal":
            proposal = self.store.get(args[0] if args else "")
            if proposal is None or proposal["client_id"] != self.client["client_id"]:
                raise Refused("unknown proposal")
            return {"source": "broker_state", "observed_at": self._now(),
                    "proposal": self._public(proposal)}
        if "." in verb:
            adapter_name, sub = verb.split(".", 1)
            cfg = self.policy["adapters"].get(adapter_name)
            if not cfg or not cfg.get("enabled"):
                raise Refused("adapter is not enabled: %s" % adapter_name)
            try:
                return self._adapter(adapter_name).read(self.client, sub, args)
            except AdapterError as exc:
                raise Refused(str(exc))
        raise Refused("unknown read verb: %s" % verb)

    def list_proposals(self, actor, limit=20):
        self._require_read(actor)
        self._expire()
        return [self._summary(p) for p in self.store.list_recent(limit)]

    def show(self, actor, proposal_id):
        self._require_read(actor)
        self._expire()
        proposal = self.store.get(proposal_id)
        if proposal is None or proposal["client_id"] != self.client["client_id"]:
            raise Refused("unknown proposal")
        return self._public(proposal)

    def status(self, actor, proposal_id):
        return self.show(actor, proposal_id)

    def reject(self, actor, proposal_id, reason=""):
        self._require_approve(actor)
        self._expire()
        proposal = self.store.get(proposal_id)
        if proposal is None or proposal["client_id"] != self.client["client_id"]:
            raise Refused("unknown proposal")
        if proposal["status"] != "PROPOSED":
            raise Refused("proposal is not awaiting approval")
        self.store.update(proposal_id, status="REJECTED", approver=actor.name,
                          execution_finished_at=self._now(), result_summary=clamp(reason or "rejected"))
        self._receipt(self.store.get(proposal_id), "REJECTED", actor.name, None)
        self._log("rejected", proposal_id=proposal_id, approver=actor.name)
        return {"proposal_id": proposal_id, "status": "REJECTED"}

    def cancel(self, actor, proposal_id):
        self._require_read(actor)
        self._expire()
        proposal = self.store.get(proposal_id)
        if proposal is None or proposal["client_id"] != self.client["client_id"]:
            raise Refused("unknown proposal")
        if proposal["request_uid"] != actor.uid and not actor.can_approve:
            raise Refused("only the requester or an approver may cancel")
        if proposal["status"] != "PROPOSED":
            raise Refused("proposal is not awaiting approval")
        self.store.update(proposal_id, status="CANCELLED", execution_finished_at=self._now(),
                          result_summary="cancelled")
        self._receipt(self.store.get(proposal_id), "CANCELLED", actor.name, None)
        self._log("cancelled", proposal_id=proposal_id, uid=actor.uid)
        return {"proposal_id": proposal_id, "status": "CANCELLED"}

    def approve(self, actor, proposal_id, confirmation=""):
        self._require_approve(actor)
        self._expire()
        proposal = self.store.get(proposal_id)
        if proposal is None or proposal["client_id"] != self.client["client_id"]:
            raise Refused("unknown proposal")
        if proposal["status"] != "PROPOSED":
            raise Refused("proposal is not awaiting approval")
        if model.plan_hash(proposal["plan"]) != proposal["execution_hash"]:
            self.store.update(proposal_id, status="FAILED", execution_finished_at=self._now(),
                              result_summary="frozen plan hash mismatch")
            raise Refused("frozen plan hash mismatch")
        if proposal["risk"] == "HIGH" and confirmation != proposal["confirmation"]:
            raise Refused("confirmation does not match; type: %s" % proposal["confirmation"])
        lock = self._lock()
        if lock is None:
            raise Refused("another execution is in progress")
        try:
            if parse_time(self._now()) >= parse_time(proposal["expires_at"]):
                self.store.update(proposal_id, status="EXPIRED", execution_finished_at=self._now(),
                                  result_summary="expired before execution")
                raise Refused("proposal expired")
            self.store.update(proposal_id, status="APPROVED", approved_at=self._now(), approver=actor.name)
            self._log("approved", proposal_id=proposal_id, approver=actor.name, risk=proposal["risk"])
            return self._execute(proposal_id, actor.name)
        finally:
            self._unlock(lock)

    def _lock(self):
        try:
            fd = os.open(self.paths.lock, os.O_CREAT | os.O_RDWR, 0o600)
        except OSError:
            raise Refused("cannot open execution lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return None
        return fd

    @staticmethod
    def _unlock(fd):
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def _execute(self, proposal_id, approver):
        proposal = self.store.get(proposal_id)
        if model.plan_hash(proposal["plan"]) != proposal["execution_hash"]:
            self.store.update(proposal_id, status="FAILED", execution_finished_at=self._now(),
                              result_summary="frozen plan hash mismatch")
            return {"proposal_id": proposal_id, "status": "FAILED", "summary": "frozen plan hash mismatch"}
        if parse_time(self._now()) >= parse_time(proposal["expires_at"]):
            self.store.update(proposal_id, status="EXPIRED", execution_finished_at=self._now(),
                              result_summary="expired before execution")
            return {"proposal_id": proposal_id, "status": "EXPIRED", "summary": "proposal expired"}
        target = self.store.inventory_get(proposal["target_id"])
        if target is None or target["client_id"] != self.client["client_id"]:
            self.store.update(proposal_id, status="FAILED", execution_finished_at=self._now(),
                              result_summary="target no longer resolves")
            return {"proposal_id": proposal_id, "status": "FAILED", "summary": "target no longer resolves"}
        self.store.update(proposal_id, status="EXECUTING", execution_started_at=self._now())
        try:
            if proposal["operation"] == "script.run":
                result = self._execute_script(proposal, target)
            elif proposal["operation"] == "plan.run":
                result = self._execute_plan(proposal, target)
            else:
                result = self._execute_operation(proposal, target)
        except (AdapterError, Refused) as exc:
            result = ExecResult(rc=1, stderr=str(exc))
        except Exception:
            LOG.exception("execution failed")
            result = ExecResult(rc=1, stderr="internal execution error")
        status = "SUCCEEDED" if result.rc == 0 else "FAILED"
        self.store.update(
            proposal_id,
            status=status,
            execution_finished_at=self._now(),
            result_rc=result.rc,
            result_summary=clamp(result.stdout or result.stderr or "", 1024),
            post_state=result.post_state,
        )
        final = self.store.get(proposal_id)
        self._receipt(final, status, approver, result)
        self._log("executed", proposal_id=proposal_id, status=status, rc=result.rc)
        return {
            "proposal_id": proposal_id,
            "status": status,
            "rc": result.rc,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def _execute_operation(self, proposal, target):
        adapter = self._adapter(proposal["adapter"])
        plan = proposal["plan"]
        stored = proposal["pre_state"] or {}
        try:
            fresh = adapter.precheck(proposal["operation"], target, proposal["parameters"])
        except AdapterError as exc:
            return ExecResult(rc=1, stderr="precheck failed: %s" % exc)
        if hasattr(adapter, "preconditions_hold") and not adapter.preconditions_hold(stored, fresh):
            return ExecResult(rc=1, stderr="target state changed; restage and reapprove",
                              pre_state=stored, post_state=fresh)
        result = adapter.execute(proposal["operation"], target, proposal["parameters"], plan)
        result.pre_state = stored
        return result

    def _execute_script(self, proposal, target):
        adapter = self._adapter(proposal["adapter"])
        script = proposal["plan"]["script"]
        script_path = script["path"]
        if os.path.islink(script_path):
            return ExecResult(rc=1, stderr="frozen script is a symlink")
        with open(script_path, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        if digest != script["sha256"]:
            return ExecResult(rc=1, stderr="frozen script hash mismatch")
        result = adapter.run_script(script["interpreter"], script_path, script["timeout_seconds"])
        result.pre_state = proposal["pre_state"] or {}
        return result

    def _execute_plan(self, proposal, target):
        steps = proposal["plan"]["steps"]
        output = []
        last = ExecResult(rc=0)
        for index, step in enumerate(steps, 1):
            step_target = self.store.inventory_get(step["target_id"])
            if step_target is None or step_target["client_id"] != self.client["client_id"]:
                last = ExecResult(rc=1, stderr="step %d: target no longer resolves" % index)
                break
            adapter = self._adapter(step["adapter"])
            op = model.get_operation(step["operation"])
            if op is None or op.name != step["operation"] or op.adapter != step["adapter"]:
                last = ExecResult(rc=1, stderr="step %d: invalid operation" % index)
                break
            if hasattr(adapter, "preconditions_hold"):
                try:
                    adapter.precheck(step["operation"], step_target, step["parameters"])
                except AdapterError as exc:
                    last = ExecResult(rc=1, stderr="step %d precheck failed: %s" % (index, exc))
                    break
            last = adapter.execute(step["operation"], step_target, step["parameters"], proposal["plan"])
            output.append("step %d %s rc=%d" % (index, step["operation"], last.rc))
            if last.rc != 0:
                break
        return ExecResult(
            rc=last.rc,
            stdout="\n".join(output) + ("\n" if output else ""),
            stderr=last.stderr,
            post_state=last.post_state,
        )

    def _summary(self, proposal, include_confirmation=False):
        out = {
            "proposal_id": proposal["proposal_id"],
            "operation": proposal["operation"],
            "target_id": proposal["target_id"],
            "target_name": proposal["target_name"],
            "risk": proposal["risk"],
            "status": proposal["status"],
            "created_at": proposal["created_at"],
            "expires_at": proposal["expires_at"],
        }
        if include_confirmation and proposal["confirmation"]:
            out["confirmation_required"] = proposal["confirmation"]
        return out

    def _public(self, proposal):
        out = {
            "proposal_id": proposal["proposal_id"],
            "client_id": proposal["client_id"],
            "site_id": proposal["site_id"],
            "operation": proposal["operation"],
            "target_id": proposal["target_id"],
            "target_name": proposal["target_name"],
            "parameters": proposal["parameters"],
            "risk": proposal["risk"],
            "status": proposal["status"],
            "created_at": proposal["created_at"],
            "expires_at": proposal["expires_at"],
            "approved_at": proposal["approved_at"],
            "approver": proposal["approver"],
            "result_rc": proposal["result_rc"],
            "result_summary": sanitize(proposal["result_summary"] or ""),
            "ai_declared": proposal["ai_declared"],
            "pre_state": proposal["pre_state"],
            "confirmation_required": proposal["confirmation"] or None,
        }
        op = model.get_operation(proposal["operation"])
        if op is not None:
            out["description"] = op.description
            out["effect"] = op.description
        if proposal["operation"] in ("script.run", "plan.run"):
            out["plan"] = proposal["plan"]
        else:
            out["executor"] = proposal["plan"].get("executor")
        return out

    def _receipt(self, proposal, status, approver, result):
        receipt = {
            "proposal_id": proposal["proposal_id"],
            "client_id": proposal["client_id"],
            "site_id": proposal["site_id"],
            "adapter": proposal["adapter"],
            "operation": proposal["operation"],
            "target_id": proposal["target_id"],
            "target_name": proposal["target_name"],
            "parameters": proposal["parameters"],
            "risk": proposal["risk"],
            "request_uid": proposal["request_uid"],
            "approver": approver,
            "created_at": proposal["created_at"],
            "approved_at": proposal["approved_at"],
            "execution_started_at": proposal["execution_started_at"],
            "execution_finished_at": proposal["execution_finished_at"],
            "execution_hash": proposal["execution_hash"],
            "pre_state": proposal["pre_state"],
            "post_state": proposal["post_state"],
            "status": status,
            "return_code": result.rc if result else None,
            "ai_declared": proposal["ai_declared"],
        }
        if result is not None:
            receipt["stdout"] = clamp(result.stdout, 16384)
            receipt["stderr"] = clamp(result.stderr, 16384)
        if proposal["operation"] == "script.run":
            script = proposal["plan"]["script"]
            receipt["script"] = {
                "sha256": script["sha256"],
                "interpreter": script["interpreter"],
                "timeout_seconds": script["timeout_seconds"],
                "transcript": clamp(result.transcript, 16384) if result else "",
            }
        os.makedirs(self.paths.receipts, mode=0o700, exist_ok=True)
        path = os.path.join(self.paths.receipts, proposal["proposal_id"] + ".json")
        tmp = path + ".tmp.%d" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(receipt, fh, sort_keys=True, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        self.store.add_receipt(proposal["proposal_id"], proposal["execution_finished_at"] or self._now(), receipt)
