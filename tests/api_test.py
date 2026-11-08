"""Сквозной тест веб-интерфейса: полный сценарий через HTTP API.

Запускается против уже работающего локального сервера:

    LTA_DATA_DIR=/tmp/lta-test python3 main.py 8765 &
    LTA_DEMO=demo.csv python3 tests/api_test.py

Проверяет: создание проекта, загрузку CSV, автоопределение типов, анонимизацию,
скачивание, деанонимизацию и побайтовое совпадение INDEX-столбцов.
"""
import csv
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

import requests

BASE = os.environ.get("LTA_BASE_URL", "http://127.0.0.1:8765").rstrip("/")
ROOT = Path(__file__).resolve().parents[1]
DEMO = Path(os.environ.get("LTA_DEMO", ROOT / "demo.csv"))
PASSWORD = "testpass123"
PROJECT = f"uitest_{uuid.uuid4().hex[:8]}"
INDEX_HEADERS = (
    "ФИО",
    "Телефон",
    "Email",
    "Дата рождения",
    "Город",
    "Адрес",
    "Паспорт",
)


def fail(message):
    print(f"  FAIL  {message}")
    sys.exit(1)


def main():
    if not DEMO.exists():
        fail(f"нет демонстрационной таблицы {DEMO}; запустите: python3 scripts/make_demo.py 5000 demo.csv")

    session = requests.Session()
    session.headers["User-Agent"] = "lta-e2e-test"

    page = session.get(BASE + "/", timeout=10)
    page.raise_for_status()
    if "Local Table Anonymizer" not in page.text:
        fail("страница приложения не загрузилась")
    if 'const TOKEN = "' not in page.text:
        fail("в странице нет API-токена")
    token = page.text.split('const TOKEN = "')[1].split('"')[0]

    # Запрос без токена должен быть отклонён.
    denied = session.get(BASE + "/api/wrong-token/state", timeout=10)
    if denied.status_code != 403:
        fail(f"запрос без корректного токена вернул {denied.status_code}, ожидался 403")

    def api(method, path, **kwargs):
        return session.request(method, BASE + f"/api/{token}{path}", timeout=30, **kwargs)

    def wait_job(job_id, timeout=120):
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = api("GET", f"/progress/{job_id}").json()
            if state.get("done"):
                return state
            time.sleep(0.25)
        fail(f"задание {job_id} не завершилось за {timeout} секунд")

    def download(name, target):
        response = session.get(BASE + f"/download/{token}/{name}", timeout=30)
        response.raise_for_status()
        target.write_bytes(response.content)
        return len(response.content)

    print(f"  base: {BASE}")
    print(f"  demo: {DEMO} ({DEMO.stat().st_size} байт)")

    state = api("GET", "/state").json()
    print(f"  state: проектов до теста — {len(state.get('projects', []))}")

    created = api("POST", "/project/create", json={"name": PROJECT, "password": PASSWORD})
    if not created.ok or not created.json().get("ok"):
        fail(f"создание проекта: {created.status_code} {created.text}")
    print(f"  проект создан: {PROJECT}")

    with DEMO.open("rb") as handle:
        uploaded = api(
            "POST",
            "/source",
            files={"file": (DEMO.name, handle, "text/csv")},
        )
    if not uploaded.ok or not uploaded.json().get("ok"):
        fail(f"загрузка таблицы: {uploaded.status_code} {uploaded.text}")
    payload = uploaded.json()
    print(f"  загружено: {payload['rows']} строк, {len(payload['headers'])} столбцов")

    state = api("GET", "/state").json()
    columns = state.get("columns", {})
    missing = [h for h in INDEX_HEADERS if h not in columns]
    if missing:
        fail(f"не найдены ожидаемые столбцы: {missing}")
    bad_modes = [h for h in INDEX_HEADERS if columns[h].get("mode") != "INDEX"]
    if bad_modes:
        fail(f"ПДн-столбцы не получили режим INDEX: {bad_modes}")
    print("  автоопределение: все ПДн-столбцы в режиме INDEX")

    started = api("POST", "/anonymize", json={}).json()
    if "job" not in started:
        fail(f"анонимизация не запустилась: {started}")
    state = wait_job(started["job"])
    if state.get("error"):
        fail(f"анонимизация: {state['error']}")
    report = state.get("report", {})
    if report.get("rows") != payload["rows"]:
        fail(f"обработано {report.get('rows')} строк вместо {payload['rows']}")
    print(f"  анонимизация: {report['rows']} строк, {len(report.get('columns', {}))} столбцов")

    with tempfile.TemporaryDirectory(prefix="lta-e2e-") as tmp:
        tmp = Path(tmp)
        anon_path = tmp / "anonymized.csv"
        anon_size = download(state["download"], anon_path)
        print(f"  скачано анонимной таблицы: {anon_size} байт")

        with anon_path.open("rb") as handle:
            uploaded = api(
                "POST",
                "/deanon/file",
                files={"file": (anon_path.name, handle, "text/csv")},
            )
        if not uploaded.ok or not uploaded.json().get("ok"):
            fail(f"загрузка анонимной таблицы: {uploaded.status_code} {uploaded.text}")

        started = api("POST", "/deanon", json={}).json()
        if "job" not in started:
            fail(f"деанонимизация не запустилась: {started}")
        state = wait_job(started["job"])
        if state.get("error"):
            fail(f"деанонимизация: {state['error']}")
        restored_report = state.get("report", {})
        if restored_report.get("not_found"):
            fail(f"не найдено псевдонимов: {restored_report['not_found']}")
        print(f"  деанонимизация: восстановлено {restored_report.get('restored', 0)} значений")

        restored_path = tmp / "restored.csv"
        download(state["download"], restored_path)

        original = list(csv.reader(DEMO.open(encoding="utf-8-sig")))
        restored = list(csv.reader(restored_path.open(encoding="utf-8-sig")))
        if len(original) != len(restored):
            fail(f"разное число строк: было {len(original)}, стало {len(restored)}")

        headers = original[0]
        index_columns = [i for i, h in enumerate(headers) if h in INDEX_HEADERS]
        mismatches = 0
        for row_number, (before, after) in enumerate(zip(original[1:], restored[1:]), start=2):
            for column in index_columns:
                if before[column] != after[column]:
                    mismatches += 1
                    if mismatches <= 5:
                        print(
                            f"    строка {row_number}, {headers[column]}: "
                            f"{before[column]!r} != {after[column]!r}"
                        )
        if mismatches:
            fail(f"расхождений в INDEX-столбцах: {mismatches}")
        print(f"  round-trip: {len(original) - 1} строк, 0 расхождений")

    destroyed = api("POST", "/project/destroy")
    if not destroyed.ok:
        print(f"  WARN  не удалось удалить тестовый проект: {destroyed.status_code}")
    else:
        print("  тестовый проект и словарь удалены")

    print("\n  OK: полный сценарий анонимизации и восстановления через веб-API работает")


if __name__ == "__main__":
    main()
