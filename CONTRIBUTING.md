# Как внести вклад

Спасибо за интерес к Local Table Anonymizer. Это небольшой локальный инструмент,
поэтому главные требования — сохранять офлайн-инварианты, обратимость `INDEX` и
предсказуемость интерфейса.

## 1. Ветки

- `main` — стабильная версия, ветка по умолчанию;
- `develop` — интеграционная ветка;
- `feature/<краткое-имя>` — новая функциональность;
- `fix/<краткое-имя>` — исправление;
- `docs/<краткое-имя>` — документация.

Ветки создаются от `develop`, завершённая работа вливается в `develop`, затем
`develop` — в `main` через merge-коммит.

## 2. Коммиты

Используются Conventional Commits:

```text
feat: add reversible index anonymization
fix: keep report tables inside the card on mobile
docs: describe the encrypted mapping format
test: cover duplicate values and wrong password
chore: add editor configuration
```

Сообщение — в императиве, на английском; тело коммита объясняет причину
изменения, если она не очевидна.

## 3. Локальные проверки

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

python3 scripts/validate.py
python3 tests/test_lta.py
bash scripts/e2e.sh
```

Для ручной проверки:

```bash
python3 scripts/make_demo.py 5000 demo.csv
LTA_DATA_DIR=/tmp/lta-dev python3 main.py 8765
```

Откройте <http://127.0.0.1:8765/> и пройдите сценарий из
[`docs/QA-CHECKLIST.md`](docs/QA-CHECKLIST.md).

## 4. Правила для данных и требований

- `references/requirements.md` — исходное ТЗ, не редактируйте его в PR.
- Все имена, телефоны, адреса, паспорта и суммы — синтетические.
- Не добавляйте реальные персональные данные, дампы, архивы и PDF.
- Не коммитьте `demo.csv`, `uitest_*`, `.env`, `opencode.json`,
  `opencodemcp.json`, `.DS_Store`, `__pycache__`.
- Если требование ТЗ не реализовано, обновите `README.md`,
  `docs/ARCHITECTURE.md` и `references/acceptance-report.md`, а не удаляйте
  требование.

## 5. Правила для приложения

- Только Python 3.11+ и зависимости из `requirements.txt`.
- Никаких сетевых запросов, внешних API, CDN, шрифтов и картинок.
- Никаких ML-библиотек и моделей.
- Сервер слушает только `127.0.0.1`.
- Словарь хранится только зашифрованным; не логируйте ПДн и пароли.
- `INDEX` должен оставаться обратимым и детерминированным.
- `HASH` и `MASK` должны оставаться необратимыми.
- Не меняйте формат `mapping.db` без миграции и обновления документации.
- Проверяйте ширины 1440, 768, 390 и 360 px.
- Сохраняйте доступность: семантическая разметка, подписи, видимый фокус,
  работа с клавиатуры.

## 6. Процесс OpenCode

Проект собран по воспроизводимой методике:

1. `/lta-plan` — план и анализ рисков без изменения файлов;
2. человек подтверждает спорные решения и объём этапа;
3. `/lta-build` — реализация согласованного этапа;
4. `/lta-qa` — независимый аудит без автоматических исправлений;
5. исправления — только после согласования.

Правила проекта — в [`AGENTS.md`](AGENTS.md), методика — в
[`.opencode/skills/local-table-anonymizer/SKILL.md`](.opencode/skills/local-table-anonymizer/SKILL.md).

## 7. Pull request

В PR укажите:

- что изменено и зачем;
- какие инварианты затронуты;
- какие проверки выполнены;
- какие ограничения остались.

CI должен быть зелёным на `main` и `develop`. PR без проверок не принимается.
