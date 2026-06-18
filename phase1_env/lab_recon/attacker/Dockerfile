# ══════════════════════════════════════════════════════════════
#  Attacker toolkit — what the student gets on their foothold.
#
#  Kept deliberately small. If you need more tools, add them here
#  rather than telling students to `apt install` (the network
#  policy in real labs blocks that anyway).
# ══════════════════════════════════════════════════════════════
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      # Network recon
      nmap \
      tcpdump \
      tshark \
      netcat-openbsd \
      iproute2 \
      iputils-ping \
      dnsutils \
      # Editing & comfort
      vim \
      less \
      jq \
      curl \
      ca-certificates \
      # Pivot toolkit (Module 3 — ssh into the engineering jumphost)
      openssh-client \
      sshpass \
      # Python for exploit modules later
      python3 \
      python3-pip \
      python3-scapy \
    && rm -rf /var/lib/apt/lists/*

# pymodbus is needed for Modules 2 & 3 — pre-install so students
# don't need internet at exploit time.
RUN pip3 install --break-system-packages \
      pymodbus==3.6.4 \
      requests

# The cold-start brief — first thing the student reads.
COPY brief.txt /brief.txt

# Drop the student into a friendly prompt that reminds them
# where they are.
RUN echo 'export PS1="\[\e[31m\]attacker@\h\[\e[0m\]:\w\$ "' \
      >> /root/.bashrc \
    && echo 'cat /brief.txt' >> /root/.bashrc

WORKDIR /root
