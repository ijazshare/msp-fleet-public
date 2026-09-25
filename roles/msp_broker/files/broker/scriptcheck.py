import re

WARNINGS = (
    (r"\brm\b", "recursive/file deletion"),
    (r"\brmdir\b", "directory removal"),
    (r"\bmkfs\b", "filesystem creation"),
    (r"\bwipefs\b", "filesystem signature wipe"),
    (r"\bdd\b", "raw device write"),
    (r"\bzfs\s+destroy\b", "ZFS dataset destruction"),
    (r"\bzpool\s+destroy\b", "ZFS pool destruction"),
    (r"\bshutdown\b", "system shutdown"),
    (r"\breboot\b", "system reboot"),
    (r"\buserdel\b", "user deletion"),
    (r"\b(iptables|nft|firewall-cmd|ufw)\b", "firewall change"),
    (r"\bchmod\s+(-[A-Za-z]+\s+)*-[A-Za-z]*R", "recursive permission change"),
    (r"\bchown\s+(-[A-Za-z]+\s+)*-[A-Za-z]*R", "recursive ownership change"),
    (r"\b(apt|apt-get)\s+(remove|purge|autoremove)\b", "package removal"),
    (r"\b(parted|fdisk|sgdisk)\b", "disk partitioning"),
    (r"authorized_keys", "SSH key change"),
    (r"\b(nohup|disown)\b", "background process escape"),
    (r"\bsystemctl\s+(enable|mask)\b", "persistent service change"),
    (r"\bcrontab\b|\bat\s+now\b|\bsystemd-run\b", "scheduled job creation"),
    (r"\bStart-Job\b|\bRegister-ScheduledTask\b|\bschtasks\b", "Windows scheduled task"),
    (r"\bRemove-Item\b|\bFormat-Volume\b", "Windows destructive operation"),
)

FORBIDDEN = (
    (r"\b(curl|wget)\b[^\n|;]*\|[^\n]*(bash|sh|python|perl|ruby)\b", "piping remote content to an interpreter"),
    (r"\biex\s*\(\s*(iwr|invoke-webrequest)\b", "piping remote content to Invoke-Expression"),
    (r"\bInvoke-Expression\b[^\n]*DownloadString", "remote content executed via Invoke-Expression"),
    (r"\bbase64\s+(-d|--decode)\b[^\n|;]*\|[^\n]*(bash|sh)\b", "decoding and piping content to a shell"),
)


def scan(text, extra_forbidden=()):
    findings = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for pattern, label in WARNINGS:
            if re.search(pattern, line):
                findings.append({"line": lineno, "severity": "HIGH", "label": label, "text": line.strip()[:160]})
        for pattern, label in FORBIDDEN:
            if re.search(pattern, line):
                findings.append({"line": lineno, "severity": "FORBIDDEN", "label": label, "text": line.strip()[:160]})
        for pattern in extra_forbidden:
            if re.search(pattern, line):
                findings.append({"line": lineno, "severity": "FORBIDDEN", "label": "policy pattern", "text": line.strip()[:160]})
    return findings
