# ══════════════════════════════════════════════════════════════
#  defender-tools — Zeek + Snort + icsnpp-modbus
#
#  One container, two tools, used in Module 4 to teach passive
#  network analysis and signature-based detection on ICS traffic.
#
#  - Zeek: protocol-aware connection logger. With icsnpp-modbus
#    extension (CISA/INL), produces register-level Modbus logs.
#  - Snort 2.9: signature-based IDS. Students write a rule that
#    alerts on Modbus traffic from non-allow-listed source IPs
#    and validate it fires only on rogue frames.
#
#  Base image: Ubuntu 22.04 (jammy) because both packages are
#  reliably available there — Debian bookworm dropped snort and
#  zeek isn't in main.
# ══════════════════════════════════════════════════════════════
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Pre-seed snort debconf so apt install doesn't prompt
RUN echo 'snort snort/address_range string 172.20.10.0/24' \
      | debconf-set-selections \
    && echo 'snort snort/interface string eth0' | debconf-set-selections \
    && echo 'snort snort/start_mode select boot' | debconf-set-selections

# Enable universe (where snort lives) and install bootstrap tools
RUN apt-get update && apt-get install -y --no-install-recommends \
      software-properties-common gnupg curl ca-certificates lsb-release \
    && add-apt-repository -y universe

# Add the official Zeek apt repo for jammy
RUN echo 'deb http://download.opensuse.org/repositories/security:/zeek/xUbuntu_22.04/ /' \
      > /etc/apt/sources.list.d/security:zeek.list \
    && curl -fsSL https://download.opensuse.org/repositories/security:zeek/xUbuntu_22.04/Release.key \
      | gpg --dearmor -o /etc/apt/trusted.gpg.d/security_zeek.gpg

RUN apt-get update && apt-get install -y --no-install-recommends \
      zeek \
      zeek-zkg \
      snort \
      git \
      python3 \
      python3-pip \
      python3-git \
      python3-semantic-version \
      tshark \
      tcpdump \
      jq \
      vim \
      less \
    && rm -rf /var/lib/apt/lists/*

# Put zeek on PATH — Ubuntu's Zeek packages install to /opt/zeek
ENV PATH="/opt/zeek/bin:${PATH}"

# ── icsnpp-modbus install (CISA/INL register-level Modbus parser) ──
# zkg's GitHub clone needs network at build time. If the layer
# fails (offline build, GitHub rate limit), stock Zeek's modbus.log
# is still produced — the lab works either way, just with less
# detail in the per-register logs.
RUN zkg autoconfig --force \
    && (zkg install --force https://github.com/cisagov/icsnpp-modbus \
        || echo "WARN: icsnpp-modbus install failed; using stock Zeek modbus parser")

# Workdir is where students drop their analysis artefacts
RUN mkdir -p /lab/work
WORKDIR /lab/work

# Friendly prompt
RUN echo 'export PATH=/opt/zeek/bin:$PATH'                       >> /root/.bashrc \
    && echo 'export PS1="\[\e[36m\]defender@\h\[\e[0m\]:\w\$ "'  >> /root/.bashrc \
    && echo 'echo "Zeek    $(zeek --version 2>&1 | head -1)"'     >> /root/.bashrc \
    && echo 'echo "Snort   $(snort --version 2>&1 | grep -E Version | head -1)"' >> /root/.bashrc \
    && echo 'echo "PCAP at /lab/pcaps/attack.pcapng"'             >> /root/.bashrc

# Keep container alive even when no shell is attached
CMD ["sleep", "infinity"]
