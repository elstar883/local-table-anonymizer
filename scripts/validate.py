#!/usr/bin/env python3
"""Проверка структуры и ограничений LTA без запуска приложения.

Скрипт использует только стандартную библиотеку, поэтому его можно запускать
до установки зависимостей. Он проверяет:
  * наличие обязательных файлов и разделов README;
  * инварианты I1–I6 в согласованном ТЗ;
  * отсутствие секретов, внешних URL и ML-библиотек в коде приложения;
  * синтаксис всех Python-файлов;
  * что локальные артефакты и секретные конфиги не попадут в репозиторий.
"""
from __future__ import annotations

import py_compile
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".md", ".yml", ".yaml", ".json", ".txt", ".toml", ".sh", ".html", ".js", ".css"}
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache", "docs/images", ".secrets"}

errors: list[str] = []
warnings: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def iter_text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in SKIP_DIRS or part.startswith(".git") for part in relative.parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {"Makefile", "LICENSE"}:
            yield path


def main() -> int:
    required = [
        "README.md",
        "LICENSE",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "AGENTS.md",
        "SECURITY.md",
        "requirements.txt",
        "requirements-dev.txt",
        "main.py",
        "lta/__init__.py",
        "lta/app.py",
        "lta/core.py",
        "lta/crypto.py",
        "lta/project.py",
        "lta/tableio.py",
        "lta/transform.py",
        "tests/test_lta.py",
        "tests/api_test.py",
        "scripts/make_demo.py",
        "scripts/e2e.sh",
        "references/requirements.md",
        ".github/workflows/tests.yml",
        ".opencode/skills/local-table-anonymizer/SKILL.md",
    ]
    for relative in required:
        check((ROOT / relative).exists(), f"нет обязательного файла: {relative}")

    # 1. Инварианты ТЗ.
    requirements = (ROOT / "references/requirements.md").read_text(encoding="utf-8")
    for invariant in ("I1.", "I2.", "I3.", "I4.", "I5.", "I6."):
        check(invariant in requirements, f"в ТЗ отсутствует инвариант {invariant}")
    for phrase in ("Полный офлайн", "Без нейросетей", "Обратимость", "Приватность словаря", "Детерминированность"):
        check(phrase in requirements, f"в ТЗ отсутствует формулировка «{phrase}»")

    # 2. README.
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for section in (
        "Проблема",
        "Что умеет приложение",
        "Быстрый старт",
        "Безопасность",
        "Workflow OpenCode",
        "Проверки и CI",
        "Структура проекта",
        "Лицензия",
    ):
        check(section.lower() in readme.lower(), f"в README нет раздела «{section}»")
    check("local-table-anonymizer" in readme, "в README нет имени репозитория")

    # 3. Секреты и запрещённые файлы.
    secret_patterns = {
        "Bearer-токен": re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}"),
        "GitHub PAT": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
        "OpenAI-подобный ключ": re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
        "AWS-ключ": re.compile(r"AKIA[0-9A-Z]{16}"),
        "приватный ключ": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    }
    for path in iter_text_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in secret_patterns.items():
            if pattern.search(text):
                errors.append(f"похоже на секрет ({name}) в {path.relative_to(ROOT)}")

    for relative in (".env", "opencode.json", "opencodemcp.json"):
        check(not (ROOT / relative).exists(), f"секретный/локальный файл не должен лежать в репозитории: {relative}")
    for pattern in ("*.pdf", "*.zip", "*.tar.gz", "*.7z"):
        for path in ROOT.rglob(pattern):
            errors.append(f"архив или PDF не должен публиковаться: {path.relative_to(ROOT)}")
    for path in ROOT.rglob(".DS_Store"):
        warnings.append(f"мусорный файл не должен публиковаться: {path.relative_to(ROOT)}")
    for path in ROOT.rglob("__pycache__"):
        warnings.append(f"кеш Python не должен публиковаться: {path.relative_to(ROOT)}")

    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for entry in (
        ".DS_Store",
        "__pycache__/",
        ".env",
        "opencode.json",
        "opencodemcp.json",
        "demo.csv",
        "uitest_",
    ):
        check(entry in gitignore, f"в .gitignore нет записи «{entry}»")

    # 4. Зависимости и версия.
    requirements_txt = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for package in ("Flask", "cryptography", "openpyxl"):
        check(package.lower() in requirements_txt.lower(), f"в requirements.txt нет {package}")
    check("<" in requirements_txt, "зависимости должны иметь верхнюю границу версии")
    init_text = (ROOT / "lta/__init__.py").read_text(encoding="utf-8")
    check('__version__ = "1.0.0"' in init_text, "версия пакета должна быть 1.0.0")

    # 5. Офлайн и отсутствие ML в коде приложения.
    app_code = "\n".join(
        p.read_text(encoding="utf-8") for p in (ROOT / "lta").glob("*.py")
    )
    for forbidden in ("import requests", "import urllib", "import httpx", "import aiohttp", "import socket"):
        check(forbidden not in app_code, f"в коде приложения найден сетевой импорт: {forbidden}")
    for ml in ("sklearn", "torch", "tensorflow", "transformers", "openai", "sentence_transformers"):
        check(ml not in app_code.lower(), f"в коде приложения найдена ML-библиотека: {ml}")
    for url in re.findall(r"https?://[^\s\"'<>]+", app_code):
        if "127.0.0.1" in url or "localhost" in url or "{host}" in url:
            continue
        # XML-пространство имён внутри data-URI SVG не является сетевым запросом.
        if url == "http://www.w3.org/2000/svg":
            continue
        errors.append(f"в коде приложения найден внешний URL: {url}")
    page_text = (ROOT / "lta/app.py").read_text(encoding="utf-8")
    check("fetch(`/api/" in page_text, "интерфейс должен обращаться только к локальному /api/")
    check("fetch(`http" not in page_text, "интерфейс не должен обращаться к внешним URL")

    # 6. Синтаксис Python.
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"синтаксическая ошибка в {path.relative_to(ROOT)}: {exc.msg}")

    # 7. Локальные артефакты: предупреждаем, но не ломаем проверку.
    for name in ("demo.csv", "uitest_anon.csv", "uitest_restored.csv"):
        if (ROOT / name).exists():
            warnings.append(f"локальный артефакт {name} существует, но исключён через .gitignore")

    if warnings:
        print("Предупреждения:")
        for warning in warnings:
            print(f"  ! {warning}")
    if errors:
        print("\nОшибки:")
        for error in errors:
            print(f"  x {error}")
        print(f"\nПроверка не пройдена: {len(errors)} ошибок")
        return 1

    print("OK: структура, инварианты, офлайн-ограничения и отсутствие секретов проверены")
    return 0


if __name__ == "__main__":
    sys.exit(main())
