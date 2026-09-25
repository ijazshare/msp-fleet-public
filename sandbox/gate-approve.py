#!/usr/bin/env python3
# Sandbox helper: drive `msp-gate step` through a pty like an operator would. Reads the printed code and types it
# (or types WRONG), optionally types a target id. Prints the gate's full output. Usage: gate-approve.py [wrong] [TARGET]
import os, pty, sys, select, re, time
wrong = "wrong" in sys.argv[1:]; target = next((a for a in sys.argv[1:] if a != "wrong"), None)
pid, fd = pty.fork()
if pid == 0:
    os.execv("/usr/local/sbin/msp-gate", ["msp-gate", "step"])
buf = b""; typed = False; typed_t = False; deadline = time.time() + 20
while time.time() < deadline:
    r, _, _ = select.select([fd], [], [], 0.5)
    if r:
        try: chunk = os.read(fd, 4096)
        except OSError: break
        if not chunk: break
        buf += chunk
        m = re.search(rb"type ([a-z0-9]{4}) to run", buf)
        if m and not typed:
            os.write(fd, (b"nope\n" if wrong else m.group(1) + b"\n")); typed = True
        if b"type the target ID" in buf and not typed_t and target is not None:
            os.write(fd, target.encode() + b"\n"); typed_t = True
sys.stdout.write(buf.decode(errors="replace")); sys.stdout.flush()
_, status = os.waitpid(pid, 0); sys.exit(os.waitstatus_to_exitcode(status))
