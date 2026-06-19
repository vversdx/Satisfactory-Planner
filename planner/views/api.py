"""API endpoints for recipe lookups, extractor options, and calculation."""
import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from ..models import Building, Item, Recipe
from ..services.preview_calculator import calculate_preview_line


def get_recipes_for_item(request, item_id):
    item = get_object_or_404(Item, id=item_id)
    recipes = Recipe.objects.filter(
        requirements__item=item,
        requirements__direction='output',
    ).select_related('building').prefetch_related('requirements__item').distinct()

    data = {
        'item': {'id': item.id, 'name': item.name, 'icon_url': item.icon.url if item.icon else ''},
        'recipes': [{
            'id': r.id, 'name': r.name, 'is_alternative': r.is_alternative,
            'building': r.building.name, 'building_id': r.building.id,
            'building_icon': r.building.icon.url if r.building.icon else '',
            'base_duration': r.base_duration, 'max_power': r.max_power,
            'inputs': [{'id': req.item.id, 'name': req.item.name, 'icon_url': req.item.icon.url if req.item.icon else '', 'amount': req.amount, 'per_minute': round(req.per_minute, 1), 'is_liquid': req.item.is_liquid} for req in r.requirements.filter(direction='input')],
            'outputs': [{'id': req.item.id, 'name': req.item.name, 'icon_url': req.item.icon.url if req.item.icon else '', 'amount': req.amount, 'per_minute': round(req.per_minute, 1), 'is_liquid': req.item.is_liquid, 'is_waste': req.is_waste} for req in r.requirements.filter(direction='output')],
        } for r in recipes],
        'can_external_input': not item.is_raw,
    }
    return JsonResponse(data)


def get_extractor_options(request, item_id):
    item = get_object_or_404(Item, id=item_id, is_raw=True)
    building_type = request.GET.get('building_type', 'extractor')
    if building_type == 'water_extractor' or (building_type == 'extractor' and 'Вода' in item.name):
        purities = [{'value': 2.0, 'label': 'Фиксированная', 'rate': 120.0}]
    else:
        base = item.extraction_rate or 30
        purities = [
            {'value': 0.5, 'label': 'Бедное', 'rate': base * 1.0},
            {'value': 1.0, 'label': 'Нормальное', 'rate': base * 2.0},
            {'value': 2.0, 'label': 'Богатое', 'rate': base * 4.0},
        ]
    data = {'item': {'id': item.id, 'name': item.name, 'icon_url': item.icon.url if item.icon else '', 'extraction_rate': item.extraction_rate}, 'purities': purities}
    return JsonResponse(data)


def get_all_items(request):
    items = Item.objects.all()
    data = {'items': [{'id': i.id, 'name': i.name, 'icon_url': i.icon.url if i.icon else '', 'is_liquid': i.is_liquid, 'is_raw': i.is_raw, 'tier': i.tier, 'extraction_rate': i.extraction_rate, 'energy_value': i.energy_value} for i in items]}
    return JsonResponse(data)


def get_all_recipes(request):
    recipes = Recipe.objects.select_related('building').prefetch_related('requirements__item').all()
    data = {'recipes': [{'id': r.id, 'name': r.name, 'building_id': r.building.id, 'building_name': r.building.name, 'building_power': r.building.base_power, 'max_power': r.max_power, 'is_alternative': r.is_alternative, 'base_duration': r.base_duration, 'inputs': [{'id': req.item.id, 'name': req.item.name, 'icon_url': req.item.icon.url if req.item.icon else '', 'amount': req.amount, 'per_minute': round(req.per_minute, 1), 'is_liquid': req.item.is_liquid} for req in r.requirements.filter(direction='input')], 'outputs': [{'id': req.item.id, 'name': req.item.name, 'icon_url': req.item.icon.url if req.item.icon else '', 'amount': req.amount, 'per_minute': round(req.per_minute, 1), 'is_liquid': req.item.is_liquid, 'is_waste': req.is_waste} for req in r.requirements.filter(direction='output')]} for r in recipes]}
    return JsonResponse(data)


def get_all_buildings(request):
    buildings = Building.objects.prefetch_related('costs__item').all()
    data = {'buildings': [{'id': b.id, 'name': b.name, 'icon_url': b.icon.url if b.icon else '', 'category': b.get_category_display() if b.category else 'other', 'category_key': b.category, 'base_power': b.base_power, 'costs': [{'item_id': c.item.id, 'item_name': c.item.name, 'amount': c.amount, 'icon_url': c.item.icon.url if c.item.icon else ''} for c in b.costs.all()]} for b in buildings]}
    return JsonResponse(data)


def calculate_preview(request):
    """API: run calculation and return results."""
    data = json.loads(request.body)
    buildings_data = data.get('buildings', [])
    connections_data = data.get('connections', [])

    # Build caches from DB directly — don't trust frontend
    items_cache = {}
    for item in Item.objects.all():
        items_cache[str(item.id)] = {
            'id': item.id, 'name': item.name,
            'energy_value': item.energy_value,
            'extraction_rate': item.extraction_rate,
            'is_liquid': item.is_liquid, 'is_raw': item.is_raw,
        }
        items_cache[item.id] = items_cache[str(item.id)]

    buildings_cache = {}
    for b in Building.objects.all():
        buildings_cache[str(b.id)] = {'id': b.id, 'name': b.name, 'category_key': b.category, 'base_power': b.base_power}
        buildings_cache[b.id] = buildings_cache[str(b.id)]

    recipes_cache = {}
    for r in Recipe.objects.prefetch_related('requirements__item').all():
        recipes_cache[str(r.id)] = {
            'id': r.id, 'name': r.name, 'building_id': r.building_id,
            'max_power': r.max_power, 'building_power': r.building.base_power,
            'inputs': [{'name': req.item.name, 'per_minute': round(req.per_minute, 1)} for req in r.requirements.filter(direction='input')],
            'outputs': [{'name': req.item.name, 'per_minute': round(req.per_minute, 1)} for req in r.requirements.filter(direction='output')],
        }
        recipes_cache[r.id] = recipes_cache[str(r.id)]

    # Convert frontend building format
    calc_buildings = []
    for b in buildings_data:
        calc_buildings.append({
            'id': b['id'],
            'type_id': b.get('type', {}).get('id', 0),
            'overclock': b.get('overclock', 1.0),
            'somersloop': b.get('somersloop', False),
            'recipe_id': b.get('recipe', {}).get('id') if b.get('recipe') else None,
            'externalInput': b.get('externalInput'),
            'resourceItem': b.get('resourceItem'),
            'resourcePurity': b.get('resourcePurity'),
            'splitterConfig': b.get('splitterConfig'),
        })

    calc_connections = []
    for c in connections_data:
        calc_connections.append({
            'from': c['from'], 'to': c['to'],
            'type': c.get('type', 'belt'), 'level': c.get('level', 1),
        })

    result = calculate_preview_line(calc_buildings, calc_connections, items_cache, buildings_cache, recipes_cache)

    return JsonResponse({
        'success': True,
        'buildings': [{'id': r.building_id, 'name': r.building_name, 'efficiency': round(r.efficiency, 3), 'power': round(r.power, 1), 'inputs': r.inputs, 'outputs': r.outputs} for r in result.buildings],
        'outputs': result.outputs,
        'total_consumption': round(result.total_consumption, 1),
        'total_generation': round(result.total_generation, 1),
        'net_balance': round(result.net_balance, 1),
        'errors': result.errors,
    })
