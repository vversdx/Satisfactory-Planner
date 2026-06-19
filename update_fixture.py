"""Update building references in initial_data.json from names to PKs."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from planner.models import Building

FIXTURE_PATH = Path('planner/fixtures/initial_data.json')

# Mapping: name in fixture -> Building.name in DB
NAME_TO_DB = {
    'Конструктор': 'Конструктор',
    'Сборщик': 'Сборщик',
    'Плавильня': 'Плавильня',
    'Литейная': 'Литейная',
    'Очистительный завод': 'Очистительный завод',
    'Смеситель': 'Смеситель',
    'Изготовитель': 'Изготовитель',
    'Упаковщик': 'Упаковщик',
    'Ускоритель частиц': 'Ускоритель частиц',
    'Преобразователь': 'Преобразователь',
    'Квантовый шифратор': 'Квантовый шифратор',
    'Угольный генератор': 'Угольный генератор',
    'Топливный генератор': 'Топливный генератор',
    'Сжигатель биомассы': 'Сжигатель биомассы',
    'Атомная электростанция': 'Атомная электростанция',
}

def main():
    name_to_pk = {b.name: b.id for b in Building.objects.all()}

    print("Buildings in DB:")
    for name, pk in name_to_pk.items():
        print(f"  {pk}: {name}")

    with open(FIXTURE_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    updated = 0
    removed = 0
    new_data = []

    for entry in data:
        if entry['model'] == 'planner.recipe':
            fixture_name = entry['fields']['building'][0]
            db_name = NAME_TO_DB.get(fixture_name)

            if not db_name:
                print(f"  SKIP: no mapping for '{fixture_name}'")
                removed += 1
                continue

            pk = name_to_pk.get(db_name)
            if not pk:
                print(f"  SKIP: '{db_name}' not in DB")
                removed += 1
                continue

            entry['fields']['building'] = pk
            updated += 1

        new_data.append(entry)

    with open(FIXTURE_PATH, 'w', encoding='utf-8') as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)

    print(f"\nUpdated: {updated} recipes")
    print(f"Removed: {removed} recipes (missing buildings)")
    print(f"\nReady for: python manage.py loaddata initial_data")

if __name__ == '__main__':
    main()
