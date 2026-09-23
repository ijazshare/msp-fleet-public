# Throwaway stand-in for the site box: Debian 12 + systemd. Not a real host (no ZFS, no PVE).
# Checks are proven against fixtures; the runner, units, heartbeat and alert path are proven for real here.
FROM debian:12
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      systemd systemd-sysv dbus python3 curl ca-certificates procps less \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && systemctl mask getty@tty1.service systemd-logind.service console-getty.service
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
