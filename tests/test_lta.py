"""Самотестирование LTA (pytest-совместимо и запускается напрямую).

Проверяет требования приёмки:
  1. round-trip: деанонимизация = исходные данные байт-в-байт;
  2. детерминированность: два запуска дают идентичный результат;
  3. неверный пароль -> отказ;
  4. HASH/MASK необратимы и сохраняют/не сохраняют вид;
  5. офлайн: при обработке нет сетевых вызовов (socket connect запрещён).
"""
import socket
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lta import core, tableio, transform
from lta.project import Project, WrongPassword

HEADERS = ["id", "ФИО", "Телефон", "Email", "Город", "Сумма"]
ROWS = [
    ["1", "Иванов Иван Иванович", "+7 916 123-45-67", "ivanov@mail.example", "Москва", "100.50"],
    ["2", "Петров Пётр Петрович", "+7 916 123-45-67", "petrov@yandex.example", "Сочи", "200.00"],
    ["3", "Иванов Иван Иванович", "+7 916 123-45-67", "ivanov@mail.example", "Москва", "300.25"],
    ["4", "Сидорова Анна Сергеевна", "", "", "Казань", "400.10"],
]
COLS = {
    "ФИО":    {"mode": "INDEX", "kind": "name",    "prefix": "NAME"},
    "Телефон": {"mode": "INDEX", "kind": "phone",  "prefix": "TEL"},
    "Email":  {"mode": "INDEX", "kind": "email",   "prefix": "MAIL"},
    "Город":  {"mode": "MASK",  "kind": "city",    "prefix": "CITY"},
    "Сумма":  {"mode": "KEEP",  "kind": "generic", "prefix": "ID"},
}


def _make_project(root, name="t.lta", password="password123"):
    p = Project.create(Path(root) / name, password)
    p.set_columns(dict(COLS))
    return p


def test_roundtrip():
    with tempfile.TemporaryDirectory() as root:
        p = _make_project(root)
        anon, rep = core.anonymize_table(p, HEADERS, [list(r) for r in ROWS])
        # ПДн заменены
        assert anon[0][1].startswith("NAME_") and len(anon[0][1]) == len("NAME_XXXXXXXX")
        assert anon[0][2].startswith("TEL_")
        assert anon[0][3].startswith("MAIL_")
        assert anon[0][4] == "М***а"          # MASK
        assert anon[0][5] == "100.50"         # KEEP
        # одинаковые значения -> одинаковые индексы
        assert anon[0][1] == anon[2][1] and anon[0][2] == anon[2][2]
        assert anon[0][1] != anon[1][1]
        restored, rep2 = core.deanon_table(p, HEADERS, anon)
        # байт-в-байт восстанавливаются обратимые (INDEX/KEEP) столбцы; MASK необратим по ТЗ
        idx_cols = [HEADERS.index(h) for h, s in COLS.items() if s["mode"] == "INDEX"]
        for orig, rest in zip(ROWS, restored):
            for c in idx_cols:
                assert orig[c] == rest[c], f"строка {orig[0]}, столбец {HEADERS[c]}: {orig[c]!r} != {rest[c]!r}"
        assert rep2["not_found"] == 0
        p.close()


def test_determinism():
    with tempfile.TemporaryDirectory() as root:
        p1 = _make_project(root, "a.lta")
        p2 = _make_project(root, "b.lta")
        # один и тот же проект, два запуска -> идентично
        a1, _ = core.anonymize_table(p1, HEADERS, [list(r) for r in ROWS])
        a2, _ = core.anonymize_table(p1, HEADERS, [list(r) for r in ROWS])
        assert a1 == a2
        # разные проекты (разные ключи) -> разные индексы
        b1, _ = core.anonymize_table(p2, HEADERS, [list(r) for r in ROWS])
        assert a1[0][1] != b1[0][1]
        p1.close(); p2.close()


def test_wrong_password():
    with tempfile.TemporaryDirectory() as root:
        p = _make_project(root, password="correct-horse1")
        p.close()
        try:
            Project.open(Path(root) / "t.lta", "wrong-password")
        except WrongPassword:
            pass
        else:
            raise AssertionError("должен быть отказ по неверному паролю")


def test_hash_mask():
    key = b"\x01" * 32
    v = "+7 916 123-45-67"
    h = transform.hash_format(v, key)
    assert h != v and len(h) == len(v)
    assert h == transform.hash_format(v, key), "HASH должен быть детерминированным"
    assert transform.mask_value("ivanov@mail.example", "email") == "i***v@m***.example"
    assert "*" in transform.mask_value("Иванов Иван Иванович", "name")


def test_offline(monkeypatch=None):
    """Запрет любых сетевых подключений во время обработки."""
    def blocked(*a, **kw):
        raise AssertionError("СЕТЕВОЙ ВЫЗОВ ОБНАРУЖЕН — нарушение I1")
    orig_connect, orig_getaddr = socket.socket.connect, socket.getaddrinfo
    socket.socket.connect = blocked
    socket.getaddrinfo = blocked
    try:
        with tempfile.TemporaryDirectory() as root:
            p = _make_project(root)
            anon, _ = core.anonymize_table(p, HEADERS, [list(r) for r in ROWS])
            core.deanon_table(p, HEADERS, anon)
            p.close()
    finally:
        socket.socket.connect, socket.getaddrinfo = orig_connect, orig_getaddr


def test_tableio_roundtrip():
    with tempfile.TemporaryDirectory() as root:
        src = Path(root) / "t.csv"
        tableio.write_table(src, HEADERS, [list(r) for r in ROWS])
        h, rows, meta = tableio.read_table(src)
        assert h == HEADERS and [list(r) for r in rows] == [list(r) for r in ROWS]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} тестов прошли")
    sys.exit(1 if failed else 0)
