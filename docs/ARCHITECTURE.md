# Архитектура Local Table Anonymizer

## 1. Назначение и инварианты

LTA — локальное приложение для обратимой анонимизации табличных данных. Архитектура
подчинена шести инвариантам из [`references/requirements.md`](../references/requirements.md):

| Инвариант | Как обеспечивается |
|---|---|
| **I1. Полный офлайн** | Flask слушает только `127.0.0.1`; весь HTML/CSS/JS встроен; в runtime нет сетевых клиентов; тест блокирует `socket.connect` и `socket.getaddrinfo`. |
| **I2. Без ML** | Только детерминированные правила: регулярные выражения, нормализация, HMAC, scrypt, HKDF, AES-GCM. Нет моделей, эмбеддингов и обучения. |
| **I3. Обратимость** | `INDEX`-значения шифруются в словарь и восстанавливаются байт-в-байт. `HASH`/`MASK` явно необратимы. |
| **I4. Псевдонимность** | Псевдоним — `PREFIX_` + 8 hex HMAC-SHA256. Без ключа исходное значение не восстанавливается. |
| **I5. Приватность словаря** | Каждый оригинал шифруется AES-256-GCM; ключ выводится из пароля через scrypt + HKDF. |
| **I6. Детерминированность** | Одинаковое значение + тот же проект + тот же столбец → тот же псевдоним. |

## 2. Компоненты

```text
main.py
  └── lta.app (Flask, встроенный UI)
        ├── lta.tableio   → чтение/запись CSV и XLSX
        ├── lta.core      → анонимизация и деанонимизация
        │     └── lta.transform → типы, нормализация, HASH, MASK
        └── lta.project  → жизненный цикл проекта и словарь
              └── lta.crypto → scrypt, HKDF, AES-GCM, HMAC
```

| Модуль | Ключевые функции | Не знает о |
|---|---|---|
| `lta.app` | маршруты `/api/<token>/...`, встроенная страница, фоновые задания | внутреннем устройстве криптографии |
| `lta.core` | `anonymize_table`, `deanon_table` | HTTP и Flask |
| `lta.transform` | `guess_kind`, `normalize`, `hash_format`, `mask_value`, `default_prefix` | проекте и ключах |
| `lta.project` | `Project.create/open/close`, `get_or_create_index`, `lookup_index`, `change_password`, `destroy` | форматах таблиц |
| `lta.crypto` | `derive_master`, `hkdf`, `encrypt`, `decrypt`, `mac`, `index_hmac`, `verifier` | таблицах и столбцах |
| `lta.tableio` | `read_table`, `write_table` | криптографии и политике обработки |

Зависимости направлены вниз: UI → core/project → crypto. `crypto` не импортирует
ничего из приложения, кроме стандартной библиотеки и `cryptography`.

## 3. Хранение

### 3.1. Каталог проекта

```text
<data-root>/projects/<name>.lta/
├── project.json   # метаданные, без ПДн
├── mapping.db     # SQLite-словарь
├── mapping.db-wal # WAL-журнал SQLite
└── mapping.db-shm # разделяемая память SQLite
```

`<data-root>` по умолчанию:

```text
~/Library/Application Support/LocalTableAnonymizer/
```

Переопределяется переменной `LTA_DATA_DIR` (используется тестами и CI).

### 3.2. `project.json`

```json
{
  "version": 1,
  "app": "LocalTableAnonymizer",
  "created_at": "2026-11-08T12:00:00",
  "kdf": { "n": 65536, "r": 8, "p": 1, "dklen": 32 },
  "salt": "<16 байт, hex>",
  "verifier": "<sha256 hex>",
  "columns": {
    "ФИО": { "mode": "INDEX", "kind": "name", "prefix": "NAME", "sample": "..." }
  }
}
```

Здесь нет исходных значений. `sample` — первый пример значения, который нужен
только для подсказки в интерфейсе; он появляется после загрузки таблицы и может
содержать ПДн. Это осознанный компромисс MVP: схема столбцов хранится рядом с
проектом, чтобы настройки переживали перезапуск. Для промышленной версии sample
стоит убрать или шифровать.

### 3.3. `mapping.db`

```sql
CREATE TABLE mapping (
    column_id  TEXT NOT NULL,
    index_val  TEXT NOT NULL,
    canon_hmac TEXT NOT NULL,
    orig_enc   BLOB NOT NULL,
    PRIMARY KEY (column_id, index_val)
);
CREATE UNIQUE INDEX ux_canon ON mapping(column_id, canon_hmac);
```

| Поле | Смысл |
|---|---|
| `column_id` | имя столбца |
| `index_val` | псевдоним, например `NAME_A1B2C3D4` |
| `canon_hmac` | HMAC канонического значения; позволяет найти дубликат без расшифровки |
| `orig_enc` | `nonce (12 байт) || AES-256-GCM ciphertext + tag` |

Поиск при деанонимизации идёт по `(column_id, index_val)`, поэтому порядок строк
в таблице не важен.

## 4. Криптографический конвейер

```text
пароль + salt
      │ scrypt(N=2^16, r=8, p=1, dklen=32)
      ▼
 master_key
      │ HKDF-SHA256(info="mapping")
      ├──────────────► mapping_key ── AES-256-GCM ──► orig_enc
      │
      │ HKDF-SHA256(info="canon-index")
      ├──────────────► canon_key ──── HMAC-SHA256 ──► canon_hmac
      │
      │ HKDF-SHA256(info="col:<column>")
      ├──────────────► column_key ─── HMAC-SHA256 ──► index_hmac
      │
      │ HKDF-SHA256(info="verify")
      └──────────────► ───────────── SHA-256 ──────► verifier
```

- **scrypt** делает перебор пароля дорогим по памяти и времени.
- **HKDF** разделяет мастер-ключ на независимые ключи для разных задач.
- **AES-256-GCM** даёт конфиденциальность и целостность; nonce уникален на
  каждую запись.
- **HMAC-SHA256** делает псевдонимы детерминированными, но необратимыми без
  ключа.
- **verifier** позволяет проверить пароль, не расшифровывая словарь.

### Коллизии

Псевдоним — 32 бита (8 hex). При коллизии `get_or_create_index` увеличивает
счётчик и пробует `HMAC(canonical|counter)`, пока не найдёт свободный псевдоним.
Уникальный индекс `(column_id, canon_hmac)` гарантирует, что одно каноническое
значение не получит два разных псевдонима.

## 5. Поток запроса

### Создание проекта

```text
POST /api/<token>/project/create {name, password}
  → Project.create()
      → salt = 16 random bytes
      → master = scrypt(password, salt)
      → project.json: kdf, salt, verifier, columns={}
      → mapping.db: CREATE TABLE
  → state.project_obj = Project
```

### Загрузка таблицы

```text
POST /api/<token>/source (multipart)
  → сохранить файл в uploads/source_<hex>.<ext>
  → tableio.read_table()
  → для каждого заголовка: transform.guess_kind(header, samples)
  → mode = INDEX для распознанных ПДн, KEEP для generic
  → project.set_columns()
```

### Анонимизация

```text
POST /api/<token>/anonymize
  → создать job_id, запустить daemon-поток
  → core.anonymize_table(project, headers, rows, progress)
      → для каждого INDEX: project.get_or_create_index()
      → для каждого HASH:  transform.hash_format()
      → для каждого MASK:  transform.mask_value()
      → для каждого KEEP:  без изменений
  → tableio.write_table(uploads/<project>_anon.<ext>)
  → progress: {frac, done, report, download}
```

UI опрашивает `GET /api/<token>/progress/<job_id>` каждые 250 мс и обновляет
`<progress>`. Задание живёт в памяти процесса; после перезапуска сервера
незавершённые задания теряются.

### Деанонимизация

```text
POST /api/<token>/deanon/file (multipart)
  → сохранить файл в uploads/deanon_<hex>.<ext>
POST /api/<token>/deanon
  → core.deanon_table(project, headers, rows, progress)
      → для каждого INDEX: project.lookup_index()
      → не найдено: значение остаётся как есть, счётчик not_found++
  → tableio.write_table(uploads/<project>_restored.<ext>)
```

## 6. Определение типов и нормализация

`guess_kind` сначала смотрит на заголовок, затем на первые 50 непустых значений:

| Тип | Признаки заголовка | Признак значения |
|---|---|---|
| `phone` | телефон, тел, phone, моб, сотов | 60% значений похожи на телефон и содержат ≥ 10 цифр |
| `email` | email, e-mail, mail, почта | 60% значений совпадают с email-regex |
| `name` | ФИО, фамилия, имя, отчество, name, клиент | — |
| `address` | адрес, address | — |
| `date` | дата рождения, birth | — |
| `passport` | паспорт, passport, СНИЛС, ИНН | — |
| `city` | город, city, населённ | — |
| `generic` | остальное | — |

Нормализация перед HMAC:

- телефон: только цифры; для 11 цифр, начинающихся с `7` или `8`, отбрасывается
  первая цифра;
- email: нижний регистр;
- остальное: схлопывание пробелов и trim.

Это позволяет считать `+7 916 123-45-67` и `89161234567` одним значением.

## 7. Обработка ошибок

| Ситуация | Поведение |
|---|---|
| Неверный пароль | `WrongPassword`, HTTP 403 в API |
| Проект уже существует | `ProjectError`, HTTP 400 |
| Неподдерживаемый формат | HTTP 400 с текстом |
| Ошибка чтения CSV/XLSX | HTTP 400, временный файл удаляется |
| Ошибка в фоновом задании | `jobs[job_id].error`, UI показывает сообщение |
| Не найден псевдоним | значение остаётся, `not_found++`, UI предупреждает |
| Нет проекта/таблицы | HTTP 400 с подсказкой, какой шаг пропущен |

## 8. Производительность

- Алгоритмы линейны по числу строк и значений.
- SQLite-словарь использует WAL и уникальные индексы.
- Прогресс обновляется не чаще, чем раз в `chunk=10000` строк.
- Текущая реализация читает файл в память целиком. Для 5000 строк и 11
  столбцов E2E занимает доли секунды; для 1 млн строк нужна потоковая версия.
- scrypt с `N=2^16` занимает заметное время при создании/открытии проекта; это
  сознательная плата за стойкость к перебору.

## 9. Соответствие ТЗ

| Требование | Статус в MVP |
|---|---|
| F1. Импорт CSV/XLSX, кодировки, разделители | реализовано |
| F1. Предпросмотр первых 20 строк | нет, только примеры по столбцам |
| F2. Режимы INDEX/HASH/MASK/KEEP | реализовано |
| F2. Префиксы и нормализация | реализовано |
| F3. HMAC-псевдонимы, коллизии | реализовано |
| F4. Зашифрованный словарь, статистика | реализовано |
| F5. Экспорт CSV/XLSX | реализовано |
| F6. Деанонимизация и отчёт | реализовано |
| F7. Потоковость, отмена | прогресс есть, потоковости и отмены нет |
| F8. Создание/открытие/смена пароля | создание и открытие есть, смены пароля в UI нет |
| F8. Сложность ≥ 10 и энтропия | минимум 8, оценки нет |
| F8. Блокировка после 3 попыток | нет |
| F9. Уничтожение проекта | реализовано, best effort |
| N1. Офлайн | реализовано и проверяется тестом |
| N2. Производительность 100k×20 | не измерялась |
| N3. macOS/Windows | macOS основной; Windows через `LTA_DATA_DIR` |
| N4. Локализация | только русский |
| N5. Логи без ПДн | отдельного `app.log` нет |
| N6. Дистрибутив | нет, запуск из исходников |

## 10. Точки расширения

- **Потоковое чтение:** заменить `read_table` на генератор и передавать строки в
  `core` порциями, не меняя формат словаря.
- **Отмена:** добавить в job флаг `cancelled` и проверять его в цикле.
- **Смена пароля в UI:** маршрут вокруг существующего
  `Project.change_password()`.
- **Блокировка попыток:** счётчик в памяти процесса или в `project.json`.
- **Новые форматы:** реализовать `read_table`/`write_table` для Parquet или
  ODS, не трогая криптографию.
- **Аудит:** писать в отдельный лог только псевдонимы, имена столбцов и
  количества, никогда — значения.
