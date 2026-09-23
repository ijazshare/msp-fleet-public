# v1 exit gate (item 6)

Deployed into each client repo as `EXIT-GATE.md`. Production work at the tax office resumes only when all six
boxes below are ticked with a date. Written 2026-09-23; target date: ____-__-__.

- [ ] **Heartbeat continuity, 14 consecutive days.** Every `msp-check@*` timer on every node pinged its own
      Healthchecks ID with no gap longer than its grace period. Proof: Healthchecks shows no DOWN event for
      any check in the window except those listed under injections below. Date: ____
- [ ] **Zero unexplained alerts in the same 14 days.** Every DOWN or `/fail` in the window is matched to a
      line in `sessions/` naming either a deliberate injection or a real fault and its fix. Date: ____
- [ ] **One PBS restore drill passed** (runbook `runbooks/pbs-restore-drill.md`): a guest restored to a
      scratch ID on a bridge with no uplink, using only the escrowed encryption key, booted, service
      answered, destroyed. Duration recorded. Date: ____
- [ ] **One box rebuild drill passed** (runbook `runbooks/rebuild-box.md`): the site box wiped and rebuilt
      from Ansible plus this repo in under 60 minutes with nothing that is not in the repo. Duration
      recorded. Date: ____
- [ ] **Gate tests passed on the real hosts**: shell as the agent account refused; stage with the cron key
      refused; never-list command refused with and without the DESTRUCTIVE label; wrong code consumes the
      stage; second stage while one is pending refused; expired stage refused; spool empty during the
      code prompt; LLM's SSH output after staging contains no code. Date: ____
- [ ] **Config-drift check caught a deliberate edit**: one comment added to a watched file produced exactly
      one alert naming that file. Date: ____

Injections and drills log (one line each, newest first):

| Date (UTC) | Node | What was done | Expected alert | Alert seen |
| --- | --- | --- | --- | --- |
