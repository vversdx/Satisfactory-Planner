"""Builder page and save/load endpoints."""
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from ..models import ProductionLine, Like, Bookmark
from ..services.calculator import calculate_line
from ..services.validators import validate_connections, validate_power_network


def build_view(request):
    return render(request, 'planner/build.html')


@login_required
@require_http_methods(['POST'])
def save_line(request):
    data = json.loads(request.body)
    line_id = data.get('line_id')

    if line_id:
        line = get_object_or_404(ProductionLine, id=line_id, author=request.user)
    else:
        line = ProductionLine(author=request.user)

    line.name = data.get('name', 'Без названия')
    line.is_published = data.get('is_published', line.is_published)
    line.total_buildings = data.get('total_buildings', 0)
    line.total_power = data.get('total_power', 0)
    line.layout_json = {
        'buildings': data.get('buildings', []),
        'connections': data.get('connections', []),
    }
    line.save()

    # Run preview calculation to get outputs
    from ..services.preview_calculator import calculate_preview_line
    from ..models import Item, Recipe, Building

    # Build caches
    items_cache = {}
    for item in Item.objects.all():
        items_cache[item.id] = {
            'id': item.id, 'name': item.name,
            'energy_value': item.energy_value,
            'extraction_rate': item.extraction_rate,
            'is_liquid': item.is_liquid, 'is_raw': item.is_raw,
        }

    buildings_cache = {}
    for b in Building.objects.all():
        buildings_cache[b.id] = {'id': b.id, 'name': b.name, 'category_key': b.category, 'base_power': b.base_power}

    recipes_cache = {}
    for r in Recipe.objects.prefetch_related('requirements__item').all():
        recipes_cache[r.id] = {
            'id': r.id, 'name': r.name, 'building_id': r.building_id,
            'max_power': r.max_power,
            'inputs': [{'name': req.item.name, 'per_minute': round(req.per_minute, 1)} for req in r.requirements.filter(direction='input')],
            'outputs': [{'name': req.item.name, 'per_minute': round(req.per_minute, 1)} for req in r.requirements.filter(direction='output')],
        }

    calc_buildings = []
    for b in data.get('buildings', []):
        calc_buildings.append({
            'id': b['id'], 'type_id': b.get('type', {}).get('id', 0),
            'overclock': b.get('overclock', 1.0),
            'somersloop': b.get('somersloop', False),
            'recipe_id': b.get('recipe', {}).get('id') if b.get('recipe') else None,
            'externalInput': b.get('externalInput'),
            'resourceItem': b.get('resourceItem'),
            'resourcePurity': b.get('resourcePurity'),
        })

    calc_connections = []
    for c in data.get('connections', []):
        calc_connections.append({
            'from': c['from'], 'to': c['to'],
            'type': c.get('type', 'belt'), 'level': c.get('level', 1),
        })

    result = calculate_preview_line(calc_buildings, calc_connections, items_cache, buildings_cache, recipes_cache)

    # Save outputs
    from ..models import LineOutput
    line.outputs.all().delete()
    for item_name, rate in result.outputs.items():
        item = Item.objects.filter(name=item_name).first()
        if item:
            LineOutput.objects.create(line=line, item=item, rate=rate)

    return JsonResponse({
        'success': True,
        'line_id': line.id,
        'message': 'Линия сохранена',
    })


@login_required
def load_line(request, line_id):
    """Load a production line for viewing or editing."""
    line = get_object_or_404(
        ProductionLine.objects.prefetch_related(
            'outputs__item',
            'likes',
            'bookmarked_by',
        ),
        id=line_id
    )

    is_author = line.author == request.user
    is_bookmarked = line.bookmarked_by.filter(user=request.user).exists()
    is_liked = line.likes.filter(user=request.user).exists()

    return render(request, 'planner/line_detail.html', {
        'line': line,
        'is_author': is_author,
        'is_bookmarked': is_bookmarked,
        'is_liked': is_liked,
    })


@login_required
@require_http_methods(['POST'])
def toggle_like(request, line_id):
    """Toggle like on a published line."""
    line = get_object_or_404(ProductionLine, id=line_id, is_published=True)
    like, created = Like.objects.get_or_create(user=request.user, line=line)

    if not created:
        like.delete()
        liked = False
    else:
        liked = True

    return JsonResponse({
        'success': True,
        'liked': liked,
        'count': line.likes.count(),
    })


@login_required
@require_http_methods(['POST'])
def toggle_bookmark(request, line_id):
    """Toggle bookmark on a published line."""
    line = get_object_or_404(ProductionLine, id=line_id, is_published=True)
    bookmark, created = Bookmark.objects.get_or_create(user=request.user, line=line)

    if not created:
        bookmark.delete()
        bookmarked = False
    else:
        bookmarked = True

    return JsonResponse({
        'success': True,
        'bookmarked': bookmarked,
    })

def get_line(request, line_id):
    line = get_object_or_404(ProductionLine, id=line_id)
    # Allow viewing if published, or if user is author
    if not line.is_published and line.author != request.user:
        return JsonResponse({'success': False, 'error': 'Нет доступа'}, status=403)

    layout = line.layout_json
    if isinstance(layout, str):
        layout = json.loads(layout)
    buildings = layout.get('buildings', [])
    return JsonResponse({
        'success': True,
        'line_id': line.id,
        'name': line.name,
        'author': line.author.username,
        'author_id': line.author.id,
        'buildings': buildings,
        'connections': layout.get('connections', []),
        'nextId': max([b['id'] for b in buildings], default=0) + 1 if buildings else 1,
    })
