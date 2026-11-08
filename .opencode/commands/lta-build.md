---
description: Реализовать один подтверждённый этап Local Table Anonymizer
agent: build
---

Реализуй только указанный ниже подтверждённый этап.

Сначала прочитай `AGENTS.md`, `references/requirements.md`,
`references/acceptance-report.md`, `docs/ARCHITECTURE.md` и `SECURITY.md`.

Правила:

- не нарушай инварианты I1–I6;
- не добавляй сетевые запросы, внешние API, CDN, шрифты и картинки;
- не добавляй ML-библиотеки и модели;
- не логируй ПДн и пароли;
- не меняй `references/requirements.md`;
- не коммить `demo.csv`, `uitest_*`, `.env`, `opencode.json`;
- не меняй формат `mapping.db` без миграции;
- сохраняй обратимость `INDEX` и необратимость `HASH`/`MASK`;
- не переписывай работающие части без необходимости;
- после работы перечисли изменённые файлы;
- запусти `python3 scripts/validate.py`, `python3 tests/test_lta.py` и
  `bash scripts/e2e.sh`;
- для UI проверь 1440, 768, 390 и 360 px;
- явно сообщи, что осталось на следующий этап.

Этап для реализации: $ARGUMENTS
