import json
import logging
import os
import signal
import socket
import struct
import threading

from .adapters import Refused
from .authorize import actor_for

LOG = logging.getLogger("msp-broker")
MAX_REQUEST = 1 << 20


class BrokerServer:
    def __init__(self, service, paths, policy):
        self.service = service
        self.paths = paths
        self.policy = policy
        self.listener = None
        self.stop = threading.Event()

    def _bind(self):
        os.makedirs(self.paths.run, mode=0o770, exist_ok=True)
        os.chmod(self.paths.run, 0o770)
        try:
            import grp
            gid = grp.getgrnam("msp-broker").gr_gid
            os.chown(self.paths.run, 0, gid)
        except (KeyError, ImportError, OSError):
            gid = None
        if os.path.exists(self.paths.socket):
            st = os.lstat(self.paths.socket)
            if not (st.st_mode & 0o170000) == 0o140000:
                raise RuntimeError("refusing to replace non-socket at %s" % self.paths.socket)
            os.unlink(self.paths.socket)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(self.paths.socket)
        os.chmod(self.paths.socket, 0o660)
        if gid is not None:
            os.chown(self.paths.socket, 0, gid)
        listener.listen(16)
        listener.settimeout(1.0)
        self.listener = listener

    def serve_forever(self):
        self._bind()
        while not self.stop.is_set():
            try:
                conn, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()
        try:
            os.unlink(self.paths.socket)
        except OSError:
            pass

    def shutdown(self, *_args):
        self.stop.set()
        if self.listener is not None:
            try:
                self.listener.close()
            except OSError:
                pass

    def _peer(self, conn):
        creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        pid, uid, gid = struct.unpack("3i", creds)
        return pid, uid, gid

    def _handle(self, conn):
        try:
            conn.settimeout(900)
            data = b""
            while b"\n" not in data and len(data) <= MAX_REQUEST:
                chunk = conn.recv(65536)
                if not chunk:
                    return
                data += chunk
            line = data.split(b"\n", 1)[0]
            try:
                request = json.loads(line.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._respond(conn, {"ok": False, "error": {"code": "REFUSED", "message": "invalid request"}})
                return
            if not isinstance(request, dict):
                self._respond(conn, {"ok": False, "error": {"code": "REFUSED", "message": "invalid request"}})
                return
            _, uid, gid = self._peer(conn)
            try:
                actor = actor_for(uid, gid, self.policy)
                result = self.dispatch(actor, request.get("method"), request.get("params") or {})
                self._respond(conn, {"ok": True, "result": result})
            except Refused as exc:
                self._respond(conn, {"ok": False, "error": {"code": exc.code, "message": str(exc)}})
            except Exception:
                LOG.exception("request failed")
                self._respond(conn, {"ok": False, "error": {"code": "ERROR", "message": "internal error"}})
        finally:
            try:
                conn.close()
            except OSError:
                pass

    @staticmethod
    def _respond(conn, payload):
        conn.sendall((json.dumps(payload, sort_keys=True) + "\n").encode("utf-8"))

    def dispatch(self, actor, method, params):
        if not isinstance(params, dict):
            raise Refused("params must be an object")
        service = self.service
        if method == "read":
            return service.read(actor, params.get("verb", ""), params.get("args", []))
        if method == "propose":
            return service.propose(actor, params.get("operation", ""), params.get("target", ""),
                                   params.get("parameters", {}))
        if method == "propose_script":
            return service.propose_script(
                actor, params.get("target", ""), params.get("interpreter", ""), params.get("file", ""),
                params.get("purpose", ""), params.get("effects", ""), params.get("timeout"),
            )
        if method == "propose_plan":
            return service.propose_plan(actor, params.get("steps", []), params.get("purpose", ""))
        if method == "list":
            return service.list_proposals(actor, params.get("limit", 20))
        if method == "show":
            return service.show(actor, params.get("proposal_id", ""))
        if method == "status":
            return service.status(actor, params.get("proposal_id", ""))
        if method == "approve":
            return service.approve(actor, params.get("proposal_id", ""), params.get("confirmation", ""))
        if method == "reject":
            return service.reject(actor, params.get("proposal_id", ""), params.get("reason", ""))
        if method == "cancel":
            return service.cancel(actor, params.get("proposal_id", ""))
        raise Refused("unknown method: %s" % method)


def main(service, paths, policy):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = BrokerServer(service, paths, policy)
    signal.signal(signal.SIGTERM, server.shutdown)
    signal.signal(signal.SIGINT, server.shutdown)
    server.serve_forever()
