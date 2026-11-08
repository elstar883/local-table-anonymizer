"""Генератор синтетической тестовой таблицы (Приложение 2 ТЗ).

Создаёт demo.csv с управляемым числом дубликатов и пропусков (~2%).
Реальные ПДн не используются.
"""
import csv
import random
import sys
from pathlib import Path

SURNAMES = ["Иванов", "Петров", "Сидоров", "Кузнецов", "Смирнов", "Васильев", "Попов",
            "Михайлов", "Новиков", "Федоров", "Морозов", "Волков", "Алексеев", "Лебедев",
            "Семенов", "Егоров", "Павлов", "Степанов", "Николаев", "Орлов"]
NAMES = ["Иван", "Пётр", "Сергей", "Андрей", "Алексей", "Дмитрий", "Никита", "Максим",
         "Владимир", "Артём", "Мария", "Анна", "Елена", "Ольга", "Татьяна", "Наталья",
         "Ирина", "Светлана", "Екатерина", "Юлия"]
PATRONYMS = ["Иванович", "Петрович", "Сергеевич", "Андреевич", "Алексеевич", "Владимирович",
             "Ивановна", "Петровна", "Сергеевна", "Андреевна", "Алексеевна", "Владимировна"]
CITIES = ["Москва", "Санкт-Петербург", "Казань", "Екатеринбург", "Новосибирск", "Владивосток",
          "Сочи", "Краснодар", "Нижний Новгород", "Самара"]
STREETS = ["ул. Ленина", "ул. Пушкина", "пр. Мира", "ул. Гагарина", "ул. Советская", "б-р Космонавтов"]
DOMAINS = ["mail.example", "yandex.example", "inbox.example", "corp.example"]


def make_phone(rng):
    return f"+7 9{rng.randint(10, 99)} {rng.randint(100, 999)}-{rng.randint(10, 99)}-{rng.randint(10, 99)}"


def make_passport(rng):
    return f"{rng.randint(4000, 4999)} {rng.randint(100000, 999999)}"


def translit(s):
    table = {"а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z","и":"i",
             "й":"y","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t",
             "у":"u","ф":"f","х":"h","ц":"c","ч":"ch","ш":"sh","щ":"sch","ъ":"","ы":"y","ь":"",
             "э":"e","ю":"yu","я":"ya"}
    return "".join(table.get(c.lower(), c) for c in s)


def generate(n_people=500, n_rows=5000, seed=42, out="demo.csv"):
    rng = random.Random(seed)
    people = []
    for _ in range(n_people):
        sn, nm, pt = rng.choice(SURNAMES), rng.choice(NAMES), rng.choice(PATRONYMS)
        fio = f"{sn} {nm} {pt}"
        email = f"{translit(nm)}.{translit(sn)}{rng.randint(1,99)}@{rng.choice(DOMAINS)}"
        people.append({
            "ФИО": fio,
            "Телефон": make_phone(rng),
            "Email": email,
            "Дата рождения": f"{rng.randint(1960,2005)}-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}",
            "Город": rng.choice(CITIES),
            "Адрес": f"{rng.choice(STREETS)}, д. {rng.randint(1,200)}, кв. {rng.randint(1,200)}",
            "Паспорт": make_passport(rng),
        })
    rows = []
    for i in range(n_rows):
        p = dict(rng.choice(people))  # дубликаты людей = повторяющиеся ПДн
        row = {
            "id": i + 1,
            **p,
            "Заказ": f"ORD-{rng.randint(10000, 99999)}",
            "Сумма": f"{rng.uniform(100, 99999):.2f}",
            "Дата заказа": f"2026-{rng.randint(1,10):02d}-{rng.randint(1,28):02d}",
        }
        # ~2% пропусков
        for k in ("Телефон", "Email", "Адрес"):
            if rng.random() < 0.02:
                row[k] = ""
        rows.append(row)
    headers = list(rows[0].keys())
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)
    print(f"Создан {out}: {len(rows)} строк, {len(headers)} столбцов, "
          f"{n_people} уникальных людей (дубликаты в таблице)")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    out = sys.argv[2] if len(sys.argv) > 2 else "demo.csv"
    generate(n_rows=n, out=out)
