import json
import socket

from .adapters import Refused


def request(socket_path, method, params, timeout=900):
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(timeout)
    try:
        conn.connect(socket_path)
    except OSError as exc:
        raise Refused("cannot reach broker at %s: %s" % (socket_path, exc))
    try:
        conn.sendall((json.dumps({"method": method, "params": params}, sort_keys=True) + "\n").encode("utf-8"))
        data = b""
        while b"\n" not in data:
            chunk = conn.recv(65536)
            if not chunk:
                raise Refused("broker closed the connection")
            data += chunk
    finally:
        conn.close()
    try:
        reply = json.loads(data.split(b"\n", 1)[0].decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise Refused("invalid reply from broker")
    if not reply.get("ok"):
        error = reply.get("error") or {}
        raise Refused(error.get("message", "refused"), error.get("code", "REFUSED"))
    return reply.get("result")


def parse_params(pairs):
    out = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise Refused("--param expects key=value")
        key, _, value = pair.partition("=")
        key = key.strip()
        value = value.strip()
        if value.lstrip("-").isdigit():
            value = int(value)
        out[key] = value
    return out


def dump(result):
    print(json.dumps(result, sort_keys=True, indent=2))
