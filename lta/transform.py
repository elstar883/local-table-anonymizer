"""Алгоритмы преобразования значений (без нейросетей, только правила и HMAC).

Режимы обработки столбца:
  INDEX — полная замена на псевдоним (обратима по словарю),
  HASH  — детерминированная замена символов с сохранением вида (необратима),
  MASK  — частичное сокрытие звёздочками (необратима),
  KEEP  — оставить как есть.
"""
import hashlib
import hmac
import re

_KIND_KEYWORDS = (
    ("phone", ("телефон", "тел", "phone", "моб", "сотов")),
    ("email", ("email", "e-mail", "mail", "почта", "эл. почта")),
    ("name", ("фио", "фамилия", "имя", "отчество", "name", "customer", "клиент")),
    ("address", ("адрес", "address")),
    ("date", ("дата рожд", "датарождения", "birth", "дата рождения")),
    ("passport", ("паспорт", "passport", "снилс", "инн")),
    ("city", ("город", "city", "населенн")),
)

_PREFIX_BY_KIND = {
    "phone": "TEL",
    "email": "MAIL",
    "name": "NAME",
    "date": "DOB",
    "passport": "PSP",
    "address": "ADDR",
    "city": "CITY",
    "generic": "ID",
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[+()\-\s\d]{10,20}$")


def default_prefix(kind):
    return _PREFIX_BY_KIND.get(kind, "ID")


def guess_kind(header, values):
    """Эвристическое определение типа столбца: заголовок + паттерны значений."""
    h = str(header).strip().lower()
    for kind, keys in _KIND_KEYWORDS:
        if any(k in h for k in keys):
            return kind
    sample = [str(v).strip() for v in values if str(v).strip()][:50]
    if sample:
        if sum(1 for v in sample if _EMAIL_RE.match(v)) > len(sample) * 0.6:
            return "email"
        if sum(1 for v in sample if _PHONE_RE.match(v) and sum(c.isdigit() for c in v) >= 10) > len(sample) * 0.6:
            return "phone"
    return "generic"


def normalize(value, kind):
    """Канонизация значения перед хэшированием (улучшает совпадение дубликатов)."""
    v = str(value).strip()
    if kind == "phone":
        digits = re.sub(r"\D", "", v)
        if len(digits) == 11 and digits[0] in "78":
            digits = digits[-10:]  # убираем код страны
        return digits
    if kind == "email":
        return v.lower()
    return " ".join(v.split())


def mask_value(value, kind):
    """Частичное сокрытие (MASK) — необратимо."""
    v = str(value)
    if not v:
        return v
    if kind == "email" and "@" in v:
        local, _, domain = v.partition("@")
        l = local[0] + "***" + (local[-1] if len(local) > 1 else "")
        if "." in domain:
            head, _, tld = domain.rpartition(".")
            d = (head[0] if head else "*") + "***." + tld
        else:
            d = domain[0] + "***"
        return f"{l}@{d}"
    if kind == "phone":
        digits = re.sub(r"\D", "", v)
        if len(digits) >= 5:
            masked = digits[:3] + "*" * (len(digits) - 5) + digits[-2:]
            return masked
        return "*" * len(v)
    if kind == "name":
        return " ".join((w[0] + "***") if w else "" for w in v.split())
    if len(v) <= 2:
        return "*" * len(v)
    return v[0] + "***" + v[-1]


def hash_format(value, key):
    """Детерминированная замена с сохранением вида (HASH): цифры → цифры,
    латиница → латиница, кириллица → '*'; знаки препинания сохраняются."""
    v = str(value)
    if not v:
        return v
    stream = bytearray()
    block_i = 0
    while len(stream) < len(v):
        stream.extend(hmac.new(key, str(block_i).encode(), hashlib.sha256).digest())
        block_i += 1
    out = []
    for ch, b in zip(v, stream):
        if ch.isdigit():
            out.append(str(b % 10))
        elif "a" <= ch <= "z":
            out.append(chr(97 + b % 26))
        elif "A" <= ch <= "Z":
            out.append(chr(65 + b % 26))
        elif ch.isalpha():  # кириллица и прочие — маскируем, чтобы не утекало
            out.append("*")
        else:
            out.append(ch)
    return "".join(out)
