#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
session_token="${1:?missing IntDog session token}"
runtime_python="$project_root/.intdog-runtime/venv-linux-py312/bin/python"

export PYTHONUTF8=1
export DOMAIN_INTEL_DATA_ROOT="$project_root/DomainIntelData"
export INTDOG_PROJECT_ROOT="$project_root"
export INTDOG_SESSION_TOKEN="$session_token"
export INTDOG_DISABLE_EMAIL=1

exec "$runtime_python" -m DomainIntelWeb.api
