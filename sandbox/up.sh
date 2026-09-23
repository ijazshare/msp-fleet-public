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
docker exec msp-sandbox sh -c 'printf "[Service]\nExecStart=/usr/bin/python3 /usr/local/bin/hc-fake.py\nRestart=no\n" > /etc/systemd/system/hc-fake.service; systemctl daemon-reload; systemctl start hc-fake'
docker exec msp-sandbox git config --system --add safe.directory '*'
# a fake client repo origin with an old-style CLAUDE.md, like the real SITE repo
docker exec msp-sandbox sh -c 'git init -q --bare /srv/fake-origin.git && d=$(mktemp -d) && cd $d && git init -q . && git -c user.name=t -c user.email=t@t commit -q --allow-empty -m init && echo "# old reconciliation instructions" > CLAUDE.md && echo "# notes" > README.md && git add -A && git -c user.name=t -c user.email=t@t commit -q -m docs && git push -q /srv/fake-origin.git HEAD:master && rm -rf $d; chmod -R a+rwX /srv/fake-origin.git' 2>/dev/null
echo "sandbox up"
