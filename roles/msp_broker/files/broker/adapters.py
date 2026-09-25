from dataclasses import dataclass, field


class AdapterError(Exception):
    pass


class Refused(Exception):
    def __init__(self, message, code="REFUSED"):
        super().__init__(message)
        self.code = code


@dataclass
class ExecResult:
    rc: int
    stdout: str = ""
    stderr: str = ""
    pre_state: dict = field(default_factory=dict)
    post_state: dict = field(default_factory=dict)
    transcript: str = ""


class Adapter:
    name = ""
    reads = ()

    def sync_inventory(self, client, store):
        raise NotImplementedError

    def read(self, client, verb, args):
        raise AdapterError("unknown read verb: %s" % verb)

    def precheck(self, operation, target, parameters):
        return {}

    def execute(self, operation, target, parameters, plan, script_path=None):
        raise AdapterError("operation not implemented")

    def state_fingerprint(self, target):
        return {}


def sanitize(text):
    import re
    if not text:
        return ""
    text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)
    text = re.sub(
        r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization)\b(\s*[:=]\s*)(\S+)",
        r"\1\2<REDACTED>",
        text,
    )
    text = re.sub(r"(?i)(--password[= ])(\S+)", r"\1<REDACTED>", text)
    return text


def clamp(text, limit=65536):
    text = sanitize(text)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[output truncated at %d bytes]" % limit
