#!/usr/bin/env bash
# Сквозная проверка: поднимает локальный сервер на изолированном каталоге данных,
# прогоняет полный сценарий анонимизации/восстановления и удаляет временные файлы.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${LTA_E2E_PORT:-8876}"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/lta-e2e.XXXXXX")"
LOG="$TMP/server.log"
SERVER_PID=""

cleanup() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT

cd "$ROOT"

if [ ! -f demo.csv ]; then
  python3 scripts/make_demo.py 5000 demo.csv
fi

LTA_DATA_DIR="$TMP/data" python3 main.py "$PORT" >"$LOG" 2>&1 &
SERVER_PID=$!

ready=0
for _ in $(seq 1 80); do
  if curl -fsS "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
    ready=1
    break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    break
  fi
  sleep 0.25
done

if [ "$ready" -ne 1 ]; then
  echo "Сервер не запустился на порту $PORT" >&2
  cat "$LOG" >&2 || true
  exit 1
fi

set +e
LTA_BASE_URL="http://127.0.0.1:$PORT" LTA_DEMO="$ROOT/demo.csv" python3 tests/api_test.py
RC=$?
set -e

if [ "$RC" -ne 0 ]; then
  echo "--- лог сервера ---" >&2
  cat "$LOG" >&2 || true
fi
exit "$RC"
