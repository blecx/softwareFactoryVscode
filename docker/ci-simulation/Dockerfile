# Factory CI Simulation Image
# ---------------------------------------------------------------------------
# Mirrors GitHub Actions: ubuntu-latest + actions/setup-python@v6 (python 3.13)
#
# NOTE: The base OS is Debian bookworm (python:3.13-slim), not Ubuntu 24.04.
#       OS-level package differences are noted in the simulation drift report.
#       Python version matches exactly (3.13), so Python-level behaviour is
#       equivalent to the real GitHub CI environment.
# ---------------------------------------------------------------------------
FROM python:3.13-slim

LABEL factory.ci_simulation="true"
LABEL factory.ci_simulation.github_ci_base="ubuntu-latest"
LABEL factory.ci_simulation.python_version="3.13"

# Install git — required by setup.sh, local_ci_parity.py, and pytest helpers
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Trust any bind-mounted repository path so git commands work inside the container
# (needed because the bind-mounted worktree is owned by the host UID, not root)
RUN git config --global --add safe.directory "*"

# Set GITHUB_ACTIONS so parity scripts detect the simulated CI context correctly
ENV GITHUB_ACTIONS=true

WORKDIR /repo
