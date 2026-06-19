#!/usr/bin/env python3
"""
Parser for Satisfactory Docs.json into Django fixtures.

Usage:
    python parse_recipes.py ru.json
    python update_fixture.py   (to convert building names to PKs)
    python manage.py loaddata initial_data
"""
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path


MANUAL_ONLY_PATHS = [
    'BP_BuildGun.BP_BuildGun_C',
    'BP_WorkshopComponent.BP_WorkshopComponent_C',
]

BUILDING_CLASS_TO_NAME = OrderedDict([
    ('Build_ConstructorMk1', 'Конструктор'),
    ('Build_AssemblerMk1', 'Сборщик'),
    ('Build_SmelterMk1', 'Плавильня'),
    ('Build_FoundryMk1', 'Литейная'),
    ('Build_OilRefinery', 'Очистительный завод'),
    ('Build_Blender', 'Смеситель'),
    ('Build_ManufacturerMk1', 'Изготовитель'),
    ('Build_Packager', 'Упаковщик'),
    ('Build_HadronCollider', 'Ускоритель частиц'),
    ('Build_Converter', 'Преобразователь'),
    ('Build_QuantumEncoder', 'Квантовый шифратор'),
    ('Build_CoalGenerator', 'Угольный генератор'),
    ('Build_FuelGenerator', 'Топливный генератор'),
    ('Build_BioGenerator', 'Сжигатель биомассы'),
    ('Build_NuclearPowerPlant', 'Атомная электростанция'),
    ('Build_GeneratorNuclear', 'Атомная электростанция'),
])

# All sections that contain items
ITEM_SECTIONS = [
    'FGItemDescriptor',
    'FGItemDescriptorBiomass',
    'FGItemDescriptorNuclearFuel',
    'FGItemDescriptorPowerBoosterFuel',
    'FGResourceDescriptor',
    'FGPowerShardDescriptor',
]


def load_docs(filepath):
    with open(filepath, 'r', encoding='utf-16') as f:
        return json.load(f)


def clean_name(class_name, display_name, prefix='Desc_'):
    if display_name and display_name.strip():
        return display_name.strip()
    name = class_name.replace(prefix, '').replace('_C', '')
    name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    return name.strip()


def parse_ingredients(raw):
    if not raw:
        return []
    results = []
    pattern = r"([A-Za-z0-9_]+_C)'\"?\s*,\s*Amount=(\d+(?:\.\d+)?)"
    for m in re.finditer(pattern, raw):
        results.append((m.group(1), float(m.group(2))))
    return results


def get_automated_buildings(produced_in_str):
    if not produced_in_str:
        return []
    matches = re.findall(r'([A-Za-z0-9_]+_C)"', produced_in_str)
    result = []
    for m in matches:
        if any(manual in m for manual in MANUAL_ONLY_PATHS):
            continue
        for bc in BUILDING_CLASS_TO_NAME:
            if bc in m and bc not in result:
                result.append(bc)
    return result


def collect_items(data):
    """Collect ALL items from ALL item sections. Key = ClassName, unique."""
    items = OrderedDict()
    for section in data:
        nc = section.get('NativeClass', '')
        if not any(s in nc for s in ITEM_SECTIONS):
            continue
        for cls in section.get('Classes', []):
            cn = cls['ClassName']
            if cn in items:
                continue  # already collected from another section
            name = clean_name(cn, cls.get('mDisplayName', ''))
            form = cls.get('mForm', 'RF_SOLID')
            items[cn] = {
                'name': name,
                'is_liquid': form in ('RF_LIQUID', 'RF_GAS'),
                'is_raw': False,
                'tier': 0,
                'extraction_rate': None,
                'icon': f'items/{cn}.png',
                'energy_value': float(cls.get('mEnergyValue', 0)),
            }
    return items


def collect_recipes(data):
    for section in data:
        if 'FGRecipe' in section.get('NativeClass', ''):
            return section.get('Classes', [])
    return []


def mark_raw(items, recipes):
    products = set()
    for r in recipes:
        for cn, _ in parse_ingredients(r.get('mProduct', '')):
            products.add(cn)
    for cn, item in items.items():
        if cn not in products:
            item['is_raw'] = True
            nl = item['name'].lower()
            if any(w in nl for w in ['вода', 'water']):
                item['extraction_rate'] = 120.0
            elif any(w in nl for w in ['нефть', 'oil', 'crude']):
                item['extraction_rate'] = 60.0
            elif any(w in nl for w in ['газ', 'gas', 'азот', 'nitrogen']):
                item['extraction_rate'] = 60.0
            else:
                item['extraction_rate'] = 30.0


def build_fixture(all_items, recipes):
    fixture = []
    pk = 0

    # ---- Items ----
    # Map: ClassName -> name, and name -> PK
    class_to_name = {cn: data['name'] for cn, data in all_items.items()}
    name_to_pk = {}

    for cn, data in all_items.items():
        pk += 1
        name_to_pk[data['name']] = pk
        fixture.append({'model': 'planner.item', 'pk': pk, 'fields': data})

    def get_or_create_item(item_class):
        """Return PK for an item, creating it if not in all_items."""
        nonlocal pk
        if item_class in class_to_name:
            name = class_to_name[item_class]
        else:
            name = clean_name(item_class, '', 'Desc_')
            class_to_name[item_class] = name

        if name not in name_to_pk:
            pk += 1
            name_to_pk[name] = pk
            fixture.append({
                'model': 'planner.item', 'pk': pk,
                'fields': {
                    'name': name, 'is_liquid': False, 'is_raw': False,
                    'tier': 0, 'extraction_rate': None, 'icon': f'items/{item_class}.png',
                }
            })
        return name_to_pk[name]

    # ---- Recipes ----
    for r in recipes:
        automated = get_automated_buildings(r.get('mProducedIn', ''))
        if not automated:
            continue

        building_name = BUILDING_CLASS_TO_NAME.get(automated[0])
        if not building_name:
            continue

        pk += 1
        recipe_pk = pk

        inputs = parse_ingredients(r.get('mIngredients', ''))
        outputs = parse_ingredients(r.get('mProduct', ''))
        duration = float(r.get('mManufactoringDuration', 0))

        is_alt = 'Alternate' in r.get('ClassName', '') or 'Альтернативный' in r.get('mDisplayName', '')

        fixture.append({
            'model': 'planner.recipe', 'pk': recipe_pk,
            'fields': {
                'name': clean_name(r['ClassName'], r.get('mDisplayName', ''), 'Recipe_'),
                'building': [building_name],  # will be replaced by update_fixture.py
                'base_duration': duration,
                'is_alternative': is_alt,
            }
        })

        for item_class, amount in inputs:
            item_pk = get_or_create_item(item_class)
            fixture.append({
                'model': 'planner.reciperequirement',
                'fields': {
                    'recipe': recipe_pk, 'direction': 'input',
                    'item': item_pk, 'amount': amount, 'is_waste': False,
                }
            })

        for item_class, amount in outputs:
            item_pk = get_or_create_item(item_class)
            fixture.append({
                'model': 'planner.reciperequirement',
                'fields': {
                    'recipe': recipe_pk, 'direction': 'output',
                    'item': item_pk, 'amount': amount, 'is_waste': False,
                }
            })

    return fixture


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} path/to/Docs.json")
        sys.exit(1)

    docs_path = Path(sys.argv[1])
    if not docs_path.exists():
        print(f"File not found: {docs_path}")
        sys.exit(1)

    print(f"Loading {docs_path}...")
    data = load_docs(docs_path)

    items = collect_items(data)
    recipes = collect_recipes(data)

    print(f"Items found: {len(items)}")
    print(f"Recipes found: {len(recipes)}")

    mark_raw(items, recipes)

    raw_count = sum(1 for v in items.values() if v['is_raw'])
    liquid_count = sum(1 for v in items.values() if v['is_liquid'])
    print(f"  Raw: {raw_count}, Liquid: {liquid_count}")

    fixture = build_fixture(items, recipes)

    fixtures_dir = Path('planner/fixtures')
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    output_path = fixtures_dir / 'initial_data.json'

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(fixture, f, ensure_ascii=False, indent=2)

    item_count = sum(1 for e in fixture if e['model'] == 'planner.item')
    recipe_count = sum(1 for e in fixture if e['model'] == 'planner.recipe')
    req_count = sum(1 for e in fixture if e['model'] == 'planner.reciperequirement')

    print(f"\nFixture: {item_count} items, {recipe_count} recipes, {req_count} requirements")
    print(f"Written to: {output_path}")
    print("\nNext: python update_fixture.py && python manage.py loaddata initial_data")


if __name__ == '__main__':
    main()
