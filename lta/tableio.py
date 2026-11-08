"""Чтение/запись таблиц CSV и XLSX (только локальные файлы)."""
import csv
import io
from pathlib import Path

_ENCODINGS = ("utf-8-sig", "utf-8", "cp1251")
_DELIMITERS = ",;\t"


def read_table(path):
    """Возвращает (headers, rows, meta). rows — список списков строк."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".csv":
        data = path.read_bytes()
        text, enc = None, None
        for e in _ENCODINGS:
            try:
                text = data.decode(e)
                enc = e
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = data.decode("utf-8", errors="replace")
            enc = "utf-8 (replace)"
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=_DELIMITERS)
            delim = dialect.delimiter
        except csv.Error:
            delim = ","
        rows = list(csv.reader(io.StringIO(text), dialect=dialect))
        rows = [r for r in rows if any(c.strip() for c in r)]
        if not rows:
            raise ValueError("Пустая таблица")
        return rows[0], rows[1:], {"encoding": enc, "delimiter": delim, "ext": "csv"}

    if ext in (".xlsx", ".xlsm"):
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        raw = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
        rows = [["" if c is None else str(c) for c in r] for r in raw]
        rows = [r for r in rows if any(c.strip() for c in r)]
        if not rows:
            raise ValueError("Пустая таблица")
        return rows[0], rows[1:], {"sheet": ws.title, "ext": "xlsx"}

    raise ValueError(f"Неподдерживаемый формат файла: {ext} (нужен .csv или .xlsx)")


def write_table(path, headers, rows):
    """Запись таблицы в CSV (utf-8-sig) или XLSX."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix.lower()
    if ext in (".xlsx", ".xlsm"):
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(list(headers))
        for r in rows:
            ws.append(list(r))
        wb.save(path)
    else:
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(headers)
            w.writerows(rows)
    return path
