# MSP Fleet — Provider-Neutral AI Safety Broker

> Provenance: pasted by the operator on 2026-09-25 as the broker extension plan. This file is the
> authoritative full plan for Phase 4 onward. Implementation status lives in `docs/HANDOVER.md`; the
> decision record is `docs/SPEC.md` (its §11 is a condensed summary of this plan). The text below is
> unchanged apart from this note. Archived harness-specific notes are in `docs/HANDOVER.md`.

## Read This First

Do not redesign the entire project.

This is an extension/hardening of the existing `msp-fleet-public` architecture.

The intended environment is an SMB MSP, not government, public infrastructure, utilities, military, or safety-critical infrastructure.

The primary operator is not expected to be a Linux/programming expert.

The system should allow powerful AI-assisted administration while enforcing this rule:

> An LLM may inspect, diagnose, reason, write scripts, prepare changes, and recommend actions freely, but it must not be able to modify production/client infrastructure unless a human technician explicitly approves the specific frozen change.

The human should approve the **effect**, not be expected to type or understand complex shell syntax.

---

# 1. Existing LLM Model

The project intentionally supports arbitrary terminal-based LLM tools.

Examples:

```text
Claude Code
Gemini CLI
OpenCode
future CLI-based agents
local models
```

They run interactively using the user's normal monthly/subscription authentication when applicable.

Do NOT require API access.

Do NOT build this around:

```text
Anthropic API
OpenAI API
Google API
LangChain
provider-specific SDKs
```

OpenCode/API models may be used, but they are not required.

The broker must be completely provider-neutral.

---

# 2. Shared Agent Instructions

Continue using one canonical:

```text
AGENTS.md
```

and symlink/provider-specific instruction files to it when appropriate:

```text
CLAUDE.md
GEMINI.md
OPENCODE.md
etc.
```

These instructions tell every LLM how to use the MSP environment.

However:

> AGENTS.md is guidance, NOT a security boundary.

Assume an LLM can:

* ignore AGENTS.md;
* hallucinate;
* misunderstand instructions;
* be prompt-injected;
* generate destructive commands;
* attempt unsupported operations.

The system must remain safe even if the LLM behaves incorrectly.

---

# 3. Fundamental Architecture

Implement:

```text
                  LLM CLI
        Claude / Gemini / OpenCode
                     |
                     v
              scratch environment
                     |
           +---------+----------+
           |                    |
           v                    v
       msp-read             msp-action
           |                    |
           |                    v
           |              MSP BROKER
           |                    |
           |             Human Approval
           |                    |
           +--------------------+
                                |
                                v
                         Device Adapters
                                |
          +---------+-----------+----------+
          |         |           |          |
          v         v           v          v
       Proxmox    UniFi      Windows    Cloud/SaaS
                                      M365 / Google
```

The LLM determines:

```text
"What should we do?"
```

The broker determines:

```text
"Is this request valid?"
"What actual infrastructure object is being targeted?"
"What execution mechanism is required?"
"Does this require approval?"
"What exact frozen operation will execute?"
```

The human determines:

```text
"Do I permit this effect?"
```

---

# 4. Security Invariants

These are non-negotiable.

## 4.1 Every infrastructure write requires approval

There must be no category of AI-generated infrastructure modification that executes automatically.

This includes seemingly harmless changes.

Examples:

```text
restart service
restart workstation
reboot VM
bounce switch port
change VLAN
install package
create user
disable user
modify firewall
update configuration
run PowerShell remediation
run Bash remediation
```

All require human approval.

Reads do not.

## 4.2 LLM must not possess production write credentials

The `llm`/agent Unix account must NOT be able to read:

```text
UniFi administrator credentials
Microsoft administrator secrets
Google Workspace secrets
ConnectWise credentials
Axcient credentials
Windows administrative passwords
Linux root SSH keys
network device admin credentials
Proxmox root credentials
```

Store privileged credentials somewhere such as:

```text
/etc/msp/secrets/
```

Permissions:

```text
root:root
0700 directory
0600 files
```

Prefer systemd credential mechanisms where practical.

Only broker/adapters should have access.

## 4.3 LLM must not have generic sudo

No:

```text
sudo bash
sudo sh
sudo python
sudo arbitrary-command
```

The LLM interacts with privileged infrastructure through broker tools only.

## 4.4 The broker does not trust LLM-supplied metadata

Do not trust the LLM to declare:

```text
risk=LOW
client=ABC
device=server01
safe=true
read_only=true
```

The broker resolves and verifies those itself.

---

# 5. Broker Implementation

Implement the broker as a small local root-owned service on each client box.

Preferred implementation:

```text
Python 3
standard library where reasonable
systemd service
Unix domain socket
SQLite for local state
```

Avoid unnecessary frameworks.

Example:

```text
/usr/local/lib/msp-broker/
/usr/local/bin/msp-action
/usr/local/bin/msp-read
/usr/local/bin/msp-approve

/run/msp/broker.sock
/var/lib/msp-broker/
/var/log/msp-broker/
```

Broker daemon:

```text
root:root
```

LLM client communicates through the Unix socket.

Use Unix peer credentials such as `SO_PEERCRED`.

Do NOT trust a user-supplied:

```text
user=
uid=
operator=
```

field.

---

# 6. Separate Identities

At minimum distinguish:

```text
llm
ops / technician
root/broker
```

## llm

Can:

```text
use Claude/Gemini/OpenCode
write scratch files
run development tools
write scripts
analyze data
call msp-read
submit msp-action proposals
view sanitized status/results
```

Cannot:

```text
approve its own actions
read secrets
modify broker data
modify broker policy
execute production changes directly
```

## technician

Can:

```text
review pending proposals
approve
reject
inspect details
```

Technician does NOT need general root shell access for normal approval.

## broker

Has:

```text
device credentials
execution capability
action registry
inventory access
audit ownership
```

---

# 7. Broker Request Model

The LLM explicitly requests an action.

Example:

```text
msp-action propose vm.reboot --target vm_104
```

or:

```text
msp-action propose unifi.port.bounce \
    --target switch_main \
    --port 18
```

The broker does NOT monitor random terminal commands and try to infer intent.

Normal scratch commands remain normal:

```text
grep
jq
python
git
awk
sed on scratch files
compilers
analysis scripts
```

The security boundary is crossed only when `msp-action` requests production execution.

---

# 8. Action Registry

Implement a root-owned operation registry.

Conceptually:

```text
operation:
    vm.reboot

adapter:
    proxmox

risk:
    DISRUPTIVE

parameters:
    target_vm

executor:
    proxmox_adapter.reboot_vm

approval:
    required
```

The LLM does NOT provide the final executable.

---

# 9. Risk Classes

Implement:

```text
LOW
DISRUPTIVE
HIGH
FORBIDDEN
```

IMPORTANT:

Even `LOW` writes still require approval.

Risk only changes the strength/presentation of approval.

Examples:

```text
VM start                    LOW
VM reboot                   DISRUPTIVE
VM hard stop                HIGH
VM destroy                  HIGH/FORBIDDEN initially

UniFi port bounce           DISRUPTIVE
UniFi AP restart            DISRUPTIVE
UniFi VLAN removal          HIGH

Windows service restart     DISRUPTIVE
Windows reboot              DISRUPTIVE
Windows user deletion       HIGH

Printer queue clear         LOW/DISRUPTIVE
Printer factory reset       FORBIDDEN initially
```

AI cannot override risk classification.

---

# 10. Inventory

Create a local normalized inventory.

Each object gets a stable internal ID.

Examples:

```text
client_001
site_main
device_83
vm_104
switch_03
ap_07
printer_12
workstation_41
user_284
```

Display human-readable names separately.

Example:

```text
device_83
Name: SW-Office-01
Vendor: Ubiquiti
Model: USW-24-PoE
Site: Main Office
```

LLMs should preferably submit stable IDs.

Do not rely solely on arbitrary names generated by the model.

---

# 11. Inventory Resolution

If LLM asks:

```text
bounce port 18 on SW-Office-01
```

broker resolves:

```text
SW-Office-01
    ->
device_83
    ->
UniFi device ID abc123
    ->
port 18
```

Before proposal succeeds, verify:

```text
device exists
adapter exists
device belongs to this client
port exists
operation supported
```

If ambiguous:

```text
REFUSED: target is ambiguous
```

Do not guess.

---

# 12. Client/Site Binding

Each client box belongs to one client.

Store authoritative identity:

```text
/etc/msp/client.yml
```

Example:

```yaml
client_id: client_001
client_name: ABC Accounting
```

A client box must not accept requests referencing another client.

This prevents an LLM from hallucinating a cross-client target.

---

# 13. READ Architecture

Implement:

```text
msp-read
```

Reads require no approval.

Examples:

```text
msp-read inventory
msp-read device device_83
msp-read unifi clients
msp-read unifi port device_83 18
msp-read windows workstation_41 disk
msp-read printer printer_12 status
msp-read proxmox vm vm_104
```

Prefer structured JSON internally.

Human-friendly output can also be available.

---

# 14. Evidence / Hallucination Protection

Data returned to the LLM should include provenance.

Example:

```json
{
  "device": "printer_12",
  "source": "snmp",
  "observed_at": "2026-09-25T01:30:00Z",
  "status": "offline"
}
```

Another:

```json
{
  "device": "device_83",
  "source": "unifi_controller",
  "observed_at": "...",
  "port": 18,
  "crc_errors": 1284
}
```

LLM interprets observations.

LLM must not become the authoritative source of facts.

---

# 15. Proposal Lifecycle

Use states similar to:

```text
PROPOSED
APPROVED
EXECUTING
SUCCEEDED
FAILED
REJECTED
EXPIRED
CANCELLED
```

Each proposal gets:

```text
UUID
```

---

# 16. Proposal Schema

Store something similar to:

```json
{
  "version": 1,
  "proposal_id": "uuid",
  "client_id": "client_001",
  "site_id": "site_main",
  "request_uid": 1001,

  "adapter": "unifi",
  "operation": "port.bounce",

  "target_id": "device_83",
  "target_name": "SW-Office-01",

  "parameters": {
    "port": 18
  },

  "risk": "DISRUPTIVE",

  "created_at": "...",
  "expires_at": "...",

  "pre_state": {},

  "execution_plan": {},
  "execution_hash": "sha256..."
}
```

Security-relevant fields are broker-generated.

---

# 17. Freeze Before Approval

Once proposal enters `PROPOSED`, freeze it.

Calculate SHA-256 over canonical execution content.

After that:

```text
target
parameters
script
commands
files
execution data
```

cannot change.

If anything changes:

```text
approval becomes invalid
```

New proposal required.

---

# 18. Approval Expiry

Default:

```text
5 minutes
```

Configurable per risk class if needed.

Do not allow future-dated creation times supplied by LLM.

Broker generates timestamps.

---

# 19. Human Approval UX

The operator should not need to type Linux commands.

Example:

```text
=================================================
CHANGE REQUEST
=================================================

CLIENT
ABC Accounting

SITE
Main Office

DEVICE
SW-Office-01

RESOURCE
Port 18 — AP-FrontOffice

ACTION
Disable and re-enable switch port

CURRENT STATE
Port up
PoE active
AP-FrontOffice connected

IMPACT
AP-FrontOffice will temporarily lose power/network.
Approximately 14 clients are currently associated.
Expected interruption: 30–90 seconds.

RISK
DISRUPTIVE

REQUEST ID
71ad6...

[APPROVE]
[REJECT]
[DETAILS]
=================================================
```

V1 terminal UI may use:

```text
A = approve
R = reject
D = details
```

No shell command typing required.

---

# 20. Stronger Confirmation

For HIGH risk require semantic confirmation.

Example:

```text
Type:

DELETE VM 104
```

This is acceptable because it confirms effect.

Do not require technician to type:

```text
qm destroy 104 --purge ...
```

Human approves effects, not syntax.

---

# 21. Show Technical Details

Still provide:

```text
VIEW TECHNICAL DETAILS
```

for audit/transparency.

But the operator does not have to understand them to perform ordinary actions.

Known operations should also show deterministic impact text produced by the adapter, not LLM prose.

---

# 22. Known Operations

Start with known structured operations.

## Proxmox

Initially:

```text
vm.start
vm.shutdown
vm.reboot
vm.stop

ct.start
ct.shutdown
ct.reboot
ct.stop

zpool.scrub

service.restart
```

Do not initially expose deletion/destruction.

Reuse the existing Proxmox host safety architecture rather than replacing it unnecessarily.

---

# 23. UniFi — Priority Adapter

UniFi is widely used across the MSP environment.

Make this the first major non-Proxmox adapter.

## Read

Implement where supported:

```text
controller status
sites
gateways
switches
APs
clients
topology
switch ports
port counters
CRC/errors
PoE state
WAN status
Wi-Fi health
AP utilization
channel
firmware version
VLAN/network inventory
```

## Actions

Start conservatively:

```text
unifi.port.bounce
unifi.port.disable
unifi.port.enable

unifi.ap.restart

unifi.device.restart
```

Later:

```text
PoE cycle
client reconnect
VLAN changes
network changes
SSID changes
```

Higher-impact configuration changes require stronger approval.

Credentials must remain root/broker-only.

---

# 24. Windows Adapter

Windows workstations are common.

Initially support read operations through the best available existing mechanism.

Possible sources:

```text
ConnectWise RMM
PowerShell remoting
WinRM
local agent
```

Do not lock architecture to one.

Normalize results.

Useful reads:

```text
online/offline
OS version
uptime
CPU
RAM
disk usage
event logs
service status
network configuration
BitLocker state
pending restart
Windows Update status
logged-in user
installed applications
printer queues
```

Actions eventually:

```text
windows.service.restart
windows.reboot
windows.shutdown
windows.process.kill
windows.update.scan
windows.update.install
windows.printer.queue.clear
```

All writes require approval.

---

# 25. ConnectWise / ScreenConnect

Create adapter boundaries, even if initial implementation is limited.

Potential use:

```text
endpoint inventory
agent health
alerts
RMM telemetry
script execution
remote session metadata
```

Do not make the rest of MSP Fleet depend directly on ConnectWise-specific IDs.

Normalize them into MSP inventory IDs.

---

# 26. Axcient

Create an adapter interface for:

```text
protected devices
last successful backup
failed backup
backup age
backup health
recovery availability
```

Initially this can be read-focused.

Backup deletion or destructive recovery actions should remain unsupported until explicitly designed.

---

# 27. Printers

Generic SNMP first.

Read:

```text
online/offline
model
serial
page count
toner levels
error state
paper state
network interface
uptime
```

Where possible correlate:

```text
printer MAC
switch
switch port
IP
hostname
```

Avoid printer write operations initially.

---

# 28. Microsoft 365 Adapter

Architecture must allow future support for:

```text
users
licenses
groups
MFA/authentication status
account enabled state
mailbox information
storage
service health
```

Writes:

```text
disable account
enable account
reset sessions
group membership
license changes
```

All require approval.

Do not expose admin tokens to LLM.

---

# 29. Google Workspace Adapter

Same concept.

Reads:

```text
users
groups
licenses
account state
storage
security information where available
```

Writes:

```text
disable user
enable user
group changes
session/security actions
```

All approval-gated.

---

# 30. Complex Terminal Work

This is essential.

Structured operations will not cover every MSP problem.

The LLM must still be able to prepare elaborate terminal work.

Implement a second path:

```text
msp-action propose-script
```

Examples:

```text
Bash
PowerShell
Python
```

---

# 31. Script Workflow

LLM freely creates something such as:

```text
/tmp/msp-work/fix-123.sh
```

This is scratch space.

Then:

```text
msp-action propose-script \
    --target server_17 \
    --interpreter bash \
    --file /tmp/msp-work/fix-123.sh \
    --purpose "Repair Samba configuration"
```

Broker then:

1. confirms target exists;
2. copies script into root-owned proposal storage;
3. refuses symlinks;
4. calculates SHA-256;
5. stores exact bytes;
6. performs static checks;
7. assigns HIGH or appropriate risk;
8. creates proposal;
9. displays plan;
10. waits for technician approval.

---

# 32. Frozen Script

Example:

```text
/var/lib/msp-broker/proposals/<uuid>/script
```

Root owned.

The original scratch file is irrelevant after staging.

If AI modifies:

```text
/tmp/msp-work/fix-123.sh
```

after staging, approved execution is unaffected.

Only frozen copy may execute.

---

# 33. Script Approval Display

Example:

```text
=================================================
COMPLEX CHANGE PLAN
=================================================

CLIENT
ABC Accounting

TARGET
FILESERVER01

PURPOSE
Repair Samba configuration

INTERPRETER
bash

SCRIPT HASH
SHA256: ...

DECLARED EFFECTS
- Back up /etc/samba/smb.conf
- Modify Samba configuration
- Validate configuration
- Restart smbd
- Test service status

FILES EXPECTED TO CHANGE
/etc/samba/smb.conf

SERVICES EXPECTED TO RESTART
smbd

EXPECTED INTERRUPTION
File shares may be unavailable temporarily.

RISK
HIGH

[VIEW SCRIPT]
[VIEW STATIC ANALYSIS]
[APPROVE]
[REJECT]
=================================================
```

Clearly label LLM-provided descriptions as:

```text
AI DECLARED
```

Do not present them as broker-verified facts.

---

# 34. Static Script Analysis

Do basic deterministic scanning.

Do not pretend this makes arbitrary scripts safe.

Flag things such as:

```text
rm
rmdir
mkfs
wipefs
dd
zfs destroy
zpool destroy
shutdown
reboot
userdel
iptables/nft
firewall changes
curl/wget executing content
chmod recursive
chown recursive
package removal
disk partitioning
SSH key changes
```

Also inspect PowerShell equivalents where practical.

Present:

```text
DETECTED HIGH-RISK OPERATIONS
```

Static analysis is warning/classification only.

It is not the primary security boundary.

---

# 35. Do Not Execute Mutable Remote Content

Reject obvious patterns such as:

```text
curl URL | bash
wget ... | sh
iex(iwr ...)
```

for AI-submitted production scripts initially.

If remote content is required:

1. download into scratch;
2. stage exact downloaded artifact;
3. hash it;
4. approve frozen content.

---

# 36. Script Timeout

Every script proposal must have:

```text
maximum runtime
```

Broker-enforced.

Example default:

```text
10 minutes
```

Configurable.

No infinite hanging actions.

---

# 37. Background Process Protection

Approved script must not be allowed to escape execution by casually creating persistent background work without disclosure.

Detect/warn/block where practical:

```text
nohup
disown
systemd service creation
cron creation
at jobs
scheduled tasks
Start-Job
```

If persistence is intentionally required, treat as HIGH risk and explicitly display it.

---

# 38. Multi-Step Plans

Support frozen multi-step plans.

Example:

```text
1. Backup config
2. Apply change
3. Validate config
4. Restart service
5. Verify service
```

The plan is immutable after approval.

If a write step fails:

```text
STOP
```

Do not let the LLM silently improvise a different write.

The LLM may inspect failure afterward and submit a new proposal.

---

# 39. Adaptive Reasoning

Read-only checks may occur between steps.

But the LLM may not alter approved write steps dynamically.

If reality differs enough that a different modification is necessary:

```text
cancel/stop current plan
create new proposal
request approval again
```

---

# 40. State Revalidation

Before execution, adapter should re-check relevant state.

Example:

Proposal:

```text
reboot VM 104
state at proposal = running
```

Before execution:

```text
VM still exists?
same internal identity?
state still appropriate?
```

If significant drift occurred:

```text
REFUSED
Target state changed.
Restage/reapprove.
```

---

# 41. Preconditions

Allow adapters to attach deterministic preconditions.

Example:

```text
VM exists
VM UUID/config fingerprint matches
switch port still belongs to AP-03
user account still exists
service still installed
```

Failed precondition invalidates proposal.

---

# 42. Approval Cannot Be Replayed

Approved action:

```text
executes once
```

After:

```text
SUCCEEDED
FAILED
CANCELLED
EXPIRED
```

it cannot execute again.

A new proposal is required.

---

# 43. One Pending Change / Concurrency

For initial implementation, prioritize safety over concurrency.

It is acceptable to permit only one active execution per client box.

Use:

```text
flock
```

or equivalent.

Multiple read operations remain fine.

Later concurrency can be added safely.

---

# 44. Audit Receipts

Broker creates authoritative root-owned receipts.

Include:

```text
proposal ID
client
site
target
operation
parameters
risk
requesting Unix UID
approving technician
creation time
approval time
execution start/end
frozen hash
pre-state
post-state
result
return code
adapter
```

For scripts include:

```text
script SHA256
interpreter
execution transcript
```

AI cannot modify receipts.

---

# 45. Git Documentation

Keep existing Git-based client documentation.

But distinguish:

```text
AUTHORITATIVE AUDIT
    broker receipts

HUMAN/AI DOCUMENTATION
    Git repository
```

AI may write session notes to Git.

Git notes must not be treated as proof that an action actually occurred.

---

# 46. No Provider Dependency

Nothing below the LLM scratch environment should know whether request originated from:

```text
Claude
Gemini
OpenCode
GPT
local model
```

Optional audit data may record process name, but it must not affect authorization.

Example:

```text
Claude Code:
msp-action propose ...

Gemini:
msp-action propose ...

OpenCode:
msp-action propose ...
```

All identical.

---

# 47. Provider Switching Test

Include a simple manual acceptance test:

1. use Claude CLI to submit a proposal;
2. use Gemini CLI to submit another;
3. use OpenCode to submit another.

All must travel through exactly the same broker/security path.

No adapter should require model-specific code.

---

# 48. Network-Level Isolation — Strongly Recommended

Eventually ensure the LLM Unix account cannot directly connect to infrastructure management networks.

The LLM needs internet access for Claude/Gemini/etc.

Therefore do NOT simply block networking.

Instead consider nftables rules based on Unix UID.

Conceptually:

```text
llm user:
    internet access = allowed
    MSP broker Unix socket = allowed
    direct client management subnet access = denied

broker:
    management subnet access = allowed
```

Example private/client networks could be configurable.

This prevents the LLM from bypassing the broker using:

```text
/usr/bin/ssh
curl
python sockets
vendor CLI
```

even if it tries.

Implement this as an optional Ansible-controlled feature first:

```yaml
msp_llm_network_isolation: false
```

Test thoroughly in SITE before enabling by default.

Do NOT break LLM provider authentication/HTTPS access.

---

# 49. Existing PVE Architecture

Do not unnecessarily throw away:

```text
ForceCommand
restricted msp-agent
read verb helpers
current gate
Ansible
sandbox tests
```

These are useful.

Refactor them where needed so the new broker can use them.

Long term:

```text
broker
    ->
Proxmox adapter
    ->
host-side restricted execution interface
```

The PVE host should still enforce its own boundary.

Defense in depth is desired.

---

# 50. Approval of Complex Proxmox/Linux Scripts

Do not give LLM root SSH private keys.

Broker owns/uses privileged connection.

LLM stages frozen script through broker.

Broker executes only after approval.

---

# 51. Secrets in Logs

Never log:

```text
passwords
OAuth refresh tokens
API keys
private keys
session cookies
```

Sanitize adapter logs.

Raw command output may contain secrets.

Design logs assuming this can happen.

---

# 52. Raw Session Recording

Do not make raw arbitrary terminal recording the primary audit mechanism.

The important audit is:

```text
proposal
approval
frozen execution
result
```

If existing session recording remains, keep retention configurable and short.

---

# 53. Broker Policy

Broker policy must be root-owned.

Example:

```text
/etc/msp/policy.yml
```

AI cannot modify.

Contains:

```text
allowed adapters
allowed operations
risk levels
timeouts
approval requirements
forbidden operations
service allowlists
network restrictions
```

---

# 54. Agent Policy

Security-critical instructions should also exist outside writable client Git.

Example:

```text
/etc/msp/agent-policy.md
```

root-owned.

AGENTS.md can explain workflow.

Root-owned policy remains authoritative.

---

# 55. Fail Closed

Examples:

```text
unknown operation       -> REFUSE
unknown target          -> REFUSE
ambiguous target        -> REFUSE
adapter failure         -> REFUSE
cannot validate state   -> REFUSE write
expired proposal        -> REFUSE
hash mismatch           -> REFUSE
wrong client            -> REFUSE
missing credential      -> REFUSE
unsupported operation   -> REFUSE
```

Do not guess.

---

# 56. Do Not Overuse Deny Lists

Keep deny lists as defense-in-depth.

Do NOT build security around trying to enumerate every dangerous shell command.

Main security boundary is:

```text
no write credential/capability
        +
broker
        +
frozen proposal
        +
human approval
```

---

# 57. User Experience Goal

Typical experience should eventually be:

Technician asks LLM:

```text
Why can't Jane print?
```

LLM reads:

```text
Jane-PC online
printer offline
switch port up
high packet loss
14 queued jobs
```

LLM proposes:

```text
Bounce UniFi port 14.
```

Technician sees:

```text
CLIENT
ABC Dental

DEVICE
SW-Office

PORT
14

CONNECTED DEVICE
HP Front Office Printer

ACTION
Power/network cycle port

IMPACT
Printer will disconnect for approximately 30–90 seconds.

APPROVE / REJECT
```

Technician approves.

No UniFi command/API knowledge required.

---

# 58. Complex UX Goal

Technician asks:

```text
Fix the Samba issue.
```

LLM:

1. diagnoses;
2. writes script;
3. tests locally where possible;
4. stages frozen script;
5. broker displays target/effects;
6. human approves;
7. broker executes;
8. output captured;
9. state verified;
10. LLM interprets result.

Technician does not manually type the Bash commands.

---

# 59. Primary Principle

Design around these three statements:

```text
LLMs reason.
Deterministic software verifies.

Humans approve effects.
They do not need to memorize syntax.

LLM providers are replaceable.
They do not own credentials, policy, state, or execution.
```

---

# 60. Implementation Phases

Do NOT attempt every integration in one pass.

## PHASE 1 — Broker Core

Implement:

```text
broker daemon
Unix socket
msp-action
msp-read
msp-approve
SQLite proposal state
UUID proposals
risk classes
freeze/hash
expiry
approval
execution state machine
audit receipts
unit tests
Ansible deployment
```

Use mock adapter.

Do not proceed until tests pass.

---

## PHASE 2 — Existing Proxmox Integration

Connect broker to existing PVE mechanisms.

Implement known actions:

```text
VM start/shutdown/reboot/stop
CT start/shutdown/reboot/stop
zpool scrub
approved service restart
```

Keep existing read capabilities.

Run full existing sandbox suite.

No regressions.

---

## PHASE 3 — Complex Script Mode

Implement:

```text
propose-script
frozen artifacts
SHA256
static warnings
timeouts
transcripts
single-use execution
failure-stop behavior
```

Test only in SITE initially.

---

## PHASE 4 — UniFi Adapter

Implement UniFi discovery/read inventory.

Then:

```text
port bounce
port enable/disable
AP restart
device restart
```

Test on SITE UniFi hardware.

Do not implement VLAN deletion/config changes initially.

---

## PHASE 5 — Printers

Implement SNMP discovery/read-only.

No writes required initially.

---

## PHASE 6 — Windows

Build normalized Windows read adapter.

Prefer existing RMM/remote mechanisms rather than reinventing a full RMM.

Add simple approval-gated actions afterward.

---

## PHASE 7 — ConnectWise / ScreenConnect / Axcient

Implement integrations as credentials/API access become available.

Do not block broker core on them.

---

## PHASE 8 — M365 / Google Workspace

Implement after local infrastructure path is stable.

Start read-only.

Then selected approval-gated writes.

---

## PHASE 9 — LLM Network Isolation

After broker/read adapters work reliably:

```text
enable optional UID-based private-network restrictions
```

Test provider CLI authentication still functions.

Only consider making this default after SITE validation.

---

# 61. Tests — Broker Core

Must test:

```text
PASS llm can submit proposal
PASS llm cannot approve proposal
PASS llm cannot access secret files
PASS llm cannot modify broker DB
PASS llm cannot modify broker policy
PASS llm cannot modify frozen proposal
PASS technician can approve
PASS technician can reject
PASS expired proposal cannot execute
PASS proposal executes once only
PASS replay refused
PASS hash mismatch refused
PASS ambiguous target refused
PASS unknown target refused
PASS wrong client refused
PASS unsupported operation refused
```

---

# 62. Tests — Parameter Injection

Test malicious values such as:

```text
104;id
104&&id
104|id
$(id)
`id`
../
../../etc/passwd
newline injection
null byte attempts
quotes
spaces
shell metacharacters
```

Known operations must not interpret these as shell.

---

# 63. Tests — Shell Execution

Known operations must NOT use:

```text
eval
shell=True
bash -c
sh -c
```

unless the explicit approved object is an arbitrary script proposal.

Known actions should execute structured argv.

---

# 64. Tests — Script Freeze

Test:

1. LLM stages script;
2. broker freezes/hash;
3. modify original scratch script;
4. approve proposal;
5. verify frozen original executes, not modified scratch copy.

---

# 65. Tests — Script Tampering

Modify frozen root-owned script artificially during test.

Broker must detect hash mismatch and refuse execution.

---

# 66. Tests — Failure Handling

Multi-step change:

```text
step 1 succeeds
step 2 fails
step 3 must NOT execute
```

Unless explicitly defined as safe cleanup/rollback.

---

# 67. Tests — Provider Neutrality

Manually or automatically verify broker has zero dependency on:

```text
Anthropic SDK
OpenAI SDK
Google model SDK
```

LLM CLI should interact only by shell tools.

---

# 68. Tests — UniFi

Against SITE:

```text
discover controller
discover switch
read ports
identify connected AP/device
stage port bounce
confirm nothing happens before approval
approve
verify exact port bounced
verify other ports unaffected
receipt created
```

---

# 69. Tests — No Approval, No Change

This is the most important test.

For every adapter write capability:

```text
submit action
DO NOT approve
wait
verify infrastructure unchanged
```

Make this an explicit regression test.

---

# 70. Tests — Malicious LLM Simulation

Do not only test normal usage.

Run commands as `llm` user attempting:

```text
read secrets
SSH directly using privileged key
modify broker files
modify proposal
approve own proposal
execute executor directly
change policy
replace adapter code
write to audit records
```

All must fail.

---

# 71. Existing Tests

Do not delete existing sandbox/security tests simply because the architecture changes.

Update where necessary.

Preserve the behaviors they were intended to protect.

---

# 72. Ansible

All deployment must remain Ansible-managed.

Running deployment twice should be idempotent.

Test:

```text
first run -> changes
second run -> no unexpected changes
```

---

# 73. Repository Documentation

After implementation matches tests, update:

```text
README
SPEC
architecture docs
threat model
AGENTS.md
```

Do not document features before they actually exist.

---

# 74. Threat Model Documentation

Explicitly document that the system protects primarily against:

```text
LLM hallucination
LLM prompt injection
LLM accidental destructive actions
operator command syntax mistakes
provider-specific agent behavior
cross-client hallucinated targeting
action mutation after approval
```

It does NOT guarantee protection against:

```text
malicious root administrator
fully compromised broker host/root
vendor platform compromise
human intentionally approving harmful changes
all possible zero-day vulnerabilities
```

---

# 75. Important Scope Decision

Do not turn this into:

```text
a new ConnectWise
a full RMM
a full SIEM
a full ticketing platform
a full monitoring platform
```

Use existing tools where appropriate.

MSP Fleet's job is:

```text
local client context
AI-assisted reasoning
cross-device investigation
safe privileged execution
human-controlled changes
normalized infrastructure view
```

---

# 76. Coding Style

Prioritize:

```text
boring
auditable
small
deterministic
testable
explicit
```

over clever abstractions.

Security-critical code should be easy for another person to read.

Avoid giant frameworks.

---

# 77. Do Not Implement Everything Immediately

Start with Phase 1.

When Phase 1 is complete:

1. run tests;
2. show full diff;
3. show new architecture;
4. show new security boundaries;
5. show test results;
6. identify anything not completed.

Then stop and allow review before Phase 2.

Repeat per phase.

Do NOT make one giant unreviewable commit.

---

# 78. Commit Structure

Suggested:

```text
1. broker core
2. proposal/approval state machine
3. audit receipts
4. mock adapter/tests
5. Proxmox adapter
6. script execution mode
7. UniFi discovery/read
8. UniFi actions
...
```

Each commit should be independently understandable.

---

# 79. Critical Acceptance Criteria

The implementation is not successful unless all of these are true.

## A

Claude, Gemini, OpenCode, or another CLI LLM can be swapped without changing the broker.

## B

LLM has powerful normal scratch-terminal access.

## C

LLM can freely inspect authorized infrastructure.

## D

LLM can generate complicated scripts/plans.

## E

LLM cannot directly execute infrastructure modifications.

## F

Every production write passes through the broker.

## G

Every production write requires technician approval.

## H

Technician does not need to type the generated Linux/PowerShell/vendor command.

## I

Exact proposed execution is frozen before approval.

## J

Modification after approval invalidates execution.

## K

Credentials are unavailable to LLM.

## L

Known actions use deterministic adapters/argv.

## M

Complex actions execute only the exact frozen script/plan.

## N

Wrong/ambiguous targets fail closed.

## O

Approved actions cannot replay.

## P

Broker audit is independent of LLM-written Git documentation.

## Q

Existing Proxmox safety properties do not regress.

---

# 80. Final Mental Model

The system should behave as though the LLM is an extremely capable but untrusted junior technician.

It may:

```text
look
investigate
reason
write
plan
recommend
prepare
```

It may NOT independently:

```text
change
delete
restart
disable
install
remove
reconfigure
execute against production
```

The LLM hands the proposed work to a deterministic privileged system.

The privileged system validates what it can.

The technician sees:

```text
CLIENT
SITE
DEVICE
ACTION
IMPACT
RISK
```

and approves or rejects it.

Only then does the frozen action execute.

That is the architecture to implement.
