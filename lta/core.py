"""Ядро обработки: анонимизация и деанонимизация таблиц.

Обе функции потоковые (порциями), получают callback прогресса.
"""
from . import transform


def anonymize_table(project, headers, rows, progress=None, chunk=10000):
    """Заменяет ПДн по конфигурации столбцов проекта.

    Возвращает (new_rows, report), где report — статистика по столбцам.
    """
    columns = project.meta.get("columns", {})
    col_by_header = {h: (headers.index(h), spec) for h, spec in columns.items() if h in headers}

    stats = {h: {"mode": s.get("mode"), "unique": 0} for h, s in columns.items()}
    seen = {h: set() for h in columns}
    new_rows = []
    total = len(rows)
    for r_i, row in enumerate(rows):
        new_row = list(row)
        for h, (idx, spec) in col_by_header.items():
            if idx >= len(new_row):
                continue
            val = new_row[idx]
            if val is None or str(val).strip() == "":
                continue
            val = str(val)
            mode = spec.get("mode", "INDEX")
            kind = spec.get("kind", "generic")
            if mode == "INDEX":
                prefix = spec.get("prefix") or transform.default_prefix(kind)
                canonical = transform.normalize(val, kind)
                new_row[idx] = project.get_or_create_index(h, canonical, val, prefix)
            elif mode == "HASH":
                new_row[idx] = transform.hash_format(val, project.col_key(h))
            elif mode == "MASK":
                new_row[idx] = transform.mask_value(val, kind)
            if val not in seen[h]:
                seen[h].add(val)
        new_rows.append(new_row)
        if progress and (r_i % chunk == 0 or r_i == total - 1):
            progress(r_i + 1, total)
    for h, s in stats.items():
        s["unique"] = len(seen[h])
    return new_rows, {"rows": total, "columns": stats}


def deanon_table(project, headers, rows, progress=None, chunk=10000):
    """Восстанавливает ПДн из словаря по псевдонимам (только INDEX-столбцы)."""
    columns = project.meta.get("columns", {})
    targets = []
    for h, spec in columns.items():
        if spec.get("mode") == "INDEX" and h in headers:
            targets.append((h, headers.index(h), spec))
    found = {h: 0 for h, _, _ in targets}
    missing = {h: 0 for h, _, _ in targets}
    new_rows = []
    total = len(rows)
    for r_i, row in enumerate(rows):
        new_row = list(row)
        for h, idx, _spec in targets:
            if idx >= len(new_row):
                continue
            val = str(new_row[idx]).strip()
            if not val:
                continue
            orig = project.lookup_index(h, val)
            if orig is None:
                missing[h] += 1
            else:
                new_row[idx] = orig
                found[h] += 1
        new_rows.append(new_row)
        if progress and (r_i % chunk == 0 or r_i == total - 1):
            progress(r_i + 1, total)
    return new_rows, {
        "rows": total,
        "restored": sum(found.values()),
        "not_found": sum(missing.values()),
        "by_column": {h: {"restored": found[h], "not_found": missing[h]} for h, _, _ in targets},
    }
