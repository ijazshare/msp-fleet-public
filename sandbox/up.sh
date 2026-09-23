#!/bin/sh
# (Re)create the sandbox container and start the fake Healthchecks endpoint inside it.
set -eu
cd "$(dirname "$0")"
docker rm -f msp-sandbox >/dev/null 2>&1 || true
docker build -q -t msp-sandbox . >/dev/null
docker run -d --name msp-sandbox --privileged --cgroupns=host \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw --tmpfs /run --tmpfs /run/lock \
  --hostname sandbox-box msp-sandbox >/dev/null
i=0; until docker exec msp-sandbox systemctl is-system-running 2>/dev/null | grep -qE 'running|degraded'; do
  i=$((i+1)); [ $i -gt 20 ] && { echo "sandbox did not boot"; docker logs msp-sandbox; exit 1; }; sleep 1; done
docker exec msp-sandbox mkdir -p /var/log/msp /usr/local/bin
docker cp hc-fake.py msp-sandbox:/usr/local/bin/hc-fake.py
docker exec msp-sandbox systemd-run --quiet --unit hc-fake python3 /usr/local/bin/hc-fake.py
echo "sandbox up"
