"""
Lightweight calculator for production line preview.
Demand-aware distribution: proportional to needs, overflow to receivers.
"""
from collections import defaultdict
from dataclasses import dataclass, field


BELT_SPEEDS = {1: 60, 2: 120, 3: 270, 4: 480, 5: 780}
PIPE_SPEEDS = {1: 300, 2: 600}
OVERCLOCK_EXPONENT = 1.321928
IDLE_POWER_FRACTION = 0.1
SOMERSLOOP_OUTPUT_MULTIPLIER = 2.0
SOMERSLOOP_POWER_MULTIPLIER = 4.0
PURITY_MULTIPLIERS = {0.5: 1.0, 1.0: 2.0, 2.0: 4.0}


@dataclass
class CalcResult:
    building_id: int
    building_name: str
    efficiency: float
    power: float
    inputs: dict
    outputs: dict


@dataclass
class LineCalcResult:
    buildings: list = field(default_factory=list)
    total_consumption: float = 0.0
    total_generation: float = 0.0
    outputs: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)

    @property
    def net_balance(self):
        return self.total_generation - self.total_consumption


def calculate_preview_line(buildings_data, connections_data, items_cache, buildings_cache, recipes_cache):
    bmap = {b['id']: b for b in buildings_data}
    conn_from = defaultdict(list)
    for c in connections_data:
        conn_from[c['from']].append((c['to'], c))

    try:
        order = _topological_sort(buildings_data, connections_data)
    except Exception as e:
        return LineCalcResult(errors=[str(e)])

    incoming = defaultdict(lambda: defaultdict(float))
    results = []
    receiver_outputs = defaultdict(float)
    total_consumption = 0.0
    total_generation = 0.0

    for b_id in order:
        b = bmap[b_id]
        result = _calc_building(b, incoming, conn_from, items_cache, buildings_cache, recipes_cache)
        results.append(result)

        btype = buildings_cache.get(b.get('type_id', 0), {})
        name = btype.get('name', '')

        if 'Приёмник' in name or 'Receiver' in name:
            for item_name, rate in incoming[b_id].items():
                receiver_outputs[item_name] += rate
        elif btype.get('category_key') == 'energy':
            total_generation += abs(result.power)
        else:
            total_consumption += result.power

        _propagate_simple(b_id, result, conn_from, incoming, bmap, buildings_cache, recipes_cache, items_cache)

    return LineCalcResult(
        buildings=results,
        total_consumption=total_consumption,
        total_generation=total_generation,
        outputs=dict(receiver_outputs),
    )


def _topological_sort(buildings, connections):
    b_ids = {b['id'] for b in buildings}
    graph = defaultdict(list)
    in_degree = defaultdict(int)
    for bid in b_ids:
        in_degree[bid] = 0
    for c in connections:
        if c.get('type') in ('belt', 'pipe'):
            graph[c['from']].append(c['to'])
            in_degree[c['to']] += 1
    queue = [bid for bid, deg in in_degree.items() if deg == 0]
    order = []
    while queue:
        bid = queue.pop(0)
        order.append(bid)
        for neighbor in graph.get(bid, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    if len(order) != len(b_ids):
        raise ValueError("Цикл в соединениях!")
    return order


def _calc_building(b, incoming, conn_from, items_cache, buildings_cache, recipes_cache):
    btype = buildings_cache.get(b.get('type_id', 0), {})
    name = btype.get('name', '?')
    b_id = b['id']

    if b.get('externalInput'):
        item = b['externalInput']['item']
        return CalcResult(b_id, name, 1.0, 0.0, {}, {item['name']: b['externalInput']['rate']})

    if b.get('resourceItem'):
        return _calc_extractor(b, buildings_cache)

    if btype.get('category_key') == 'energy':
        recipe_id = b.get('recipe_id')
        if recipe_id and recipe_id in recipes_cache:
            # Has recipe — use production logic for waste outputs
            return _calc_generator_with_recipe(b, incoming, items_cache, buildings_cache, recipes_cache)
        return _calc_generator(b, incoming, items_cache, buildings_cache)

    if 'Разветвитель' in name:
        in_flows = incoming[b_id]
        return CalcResult(b_id, name, 1.0, 0.0, dict(in_flows), dict(in_flows))

    if 'Слияние' in name:
        in_flows = incoming[b_id]
        return CalcResult(b_id, name, 1.0, 0.0, dict(in_flows), dict(in_flows))

    if 'Приёмник' in name or 'Receiver' in name:
        return CalcResult(b_id, name, 1.0, 1.0, {}, {})

    recipe_id = b.get('recipe_id')
    if recipe_id and recipe_id in recipes_cache:
        return _calc_production(b, incoming, recipes_cache, buildings_cache)

    return CalcResult(b_id, name, 0.0, 0.0, {}, {})


def _calc_extractor(b, buildings_cache):
    btype = buildings_cache.get(b.get('type_id', 0), {})
    name = btype.get('name', '?')
    item = b['resourceItem']
    base_rate = item.get('extraction_rate', 30)
    purity = b.get('resourcePurity', 1.0)
    overclock = b.get('overclock', 1.0)

    if 'Экстрактор воды' in name:
        rate = 120.0 * overclock
    else:
        mult = PURITY_MULTIPLIERS.get(purity, 1.0)
        rate = base_rate * mult * overclock

    power = abs(btype.get('base_power', 0)) * (overclock ** OVERCLOCK_EXPONENT)
    return CalcResult(b['id'], name, 1.0, power, {}, {item['name']: rate})


def _calc_generator(b, incoming, items_cache, buildings_cache):
    btype = buildings_cache.get(b.get('type_id', 0), {})
    name = btype.get('name', '?')
    base_power = abs(btype.get('base_power', 0))
    overclock = b.get('overclock', 1.0)

    total_energy = 0.0
    water_rate = incoming[b['id']].get('Вода', incoming[b['id']].get('Water', 0))
    water_efficiency = 1.0

    for item_name, rate in incoming[b['id']].items():
        item = next((i for i in items_cache.values() if isinstance(i, dict) and i.get('name') == item_name), None)
        if item and item.get('energy_value', 0) > 0:
            total_energy += rate * item['energy_value'] / 60

    # Water requirement
    required_water = 0
    if 'Угольный' in name:
        required_water = 45.0 * overclock
    elif 'Атомная' in name:
        required_water = 240.0 * overclock

    if required_water > 0:
        if water_rate <= 0:
            water_efficiency = 0.0
        else:
            water_efficiency = min(1.0, water_rate / required_water)

    max_power = base_power * overclock
    actual_power = min(total_energy, max_power) * water_efficiency
    eff = actual_power / max_power if max_power > 0 else 0
    return CalcResult(b['id'], name, eff, -actual_power, dict(incoming[b['id']]), {})


def _calc_production(b, incoming, recipes_cache, buildings_cache):
    recipe = recipes_cache.get(b['recipe_id'], {})
    if not recipe:
        return CalcResult(b['id'], '?', 0.0, 0.0, {}, {})

    btype = buildings_cache.get(b.get('type_id', 0), {})
    overclock = b.get('overclock', 1.0)
    somersloop = b.get('somersloop', False)
    base_power = recipe.get('max_power', 0) or abs(btype.get('base_power', 0))

    efficiency = 1.0
    consumed = {}
    for inp in recipe.get('inputs', []):
        required = inp['per_minute'] * overclock
        available = incoming[b['id']].get(inp['name'], 0)
        if required > 0:
            efficiency = min(efficiency, available / required)
        consumed[inp['name']] = available

    outputs = {}
    if efficiency > 0:
        for out in recipe.get('outputs', []):
            rate = out['per_minute'] * overclock * efficiency
            if somersloop:
                rate *= SOMERSLOOP_OUTPUT_MULTIPLIER
            outputs[out['name']] = rate

    if efficiency > 0:
        power = base_power * (overclock ** OVERCLOCK_EXPONENT) * efficiency
        if somersloop:
            power *= SOMERSLOOP_POWER_MULTIPLIER
    else:
        power = base_power * IDLE_POWER_FRACTION

    return CalcResult(b['id'], btype.get('name', '?'), efficiency, power, consumed, outputs)


def _propagate_simple(b_id, result, conn_from, incoming, bmap, buildings_cache, recipes_cache, items_cache):
    out_conns = conn_from.get(b_id, [])

    for item_name, rate in result.outputs.items():
        if rate <= 0 or not out_conns:
            continue

        consumer_data = []
        receivers = []

        for to_id, conn_data in out_conns:
            b = bmap.get(to_id)
            btype = buildings_cache.get(b.get('type_id', 0), {}) if b else {}
            name = btype.get('name', '')

            conn_type = conn_data.get('type', 'belt')
            level = conn_data.get('level', 1)
            limit = BELT_SPEEDS.get(level, 60) if conn_type == 'belt' else PIPE_SPEEDS.get(level, 300)

            if 'Приёмник' in name or 'Receiver' in name:
                receivers.append((to_id, limit))
            else:
                need = _get_need(b, item_name, recipes_cache, items_cache, buildings_cache)
                consumer_data.append((to_id, limit, need))

        total_need = sum(n for _, _, n in consumer_data)
        remaining = rate

        if total_need > 0 and consumer_data:
            for to_id, limit, need in consumer_data:
                share = rate * (need / total_need)
                sent = min(share, limit, remaining)
                incoming[to_id][item_name] += sent
                remaining -= sent

            for _ in range(3):
                if remaining <= 0.001:
                    break
                spare_total = 0.0
                spares = []
                for to_id, limit, need in consumer_data:
                    already = incoming[to_id].get(item_name, 0)
                    spare = max(0.0, limit - already)
                    spares.append((to_id, spare))
                    spare_total += spare
                if spare_total <= 0.001:
                    break
                for to_id, spare in spares:
                    if spare > 0.001:
                        take = remaining * (spare / spare_total)
                        sent = min(take, spare)
                        incoming[to_id][item_name] += sent
                        remaining -= sent
        elif consumer_data:
            share = rate / len(consumer_data)
            for to_id, limit, _ in consumer_data:
                sent = min(share, limit, remaining)
                incoming[to_id][item_name] += sent
                remaining -= sent

        for to_id, limit in receivers:
            if remaining <= 0.001:
                break
            sent = min(remaining, limit)
            incoming[to_id][item_name] += sent
            remaining -= sent


def _get_need(b, item_name, recipes_cache, items_cache, buildings_cache):
    if not b:
        return 0.0

    btype = buildings_cache.get(b.get('type_id', 0), {})
    name = btype.get('name', '')

    if btype.get('category_key') == 'energy':
        # Water requirement for generators that need it
        if item_name == 'Вода':
            if 'Угольный' in name:
                return 45.0
            if 'Атомная' in name:
                return 240.0
            return 0.0

        # Fuel — calculate from energy value
        item = next((i for i in items_cache.values() if isinstance(i, dict) and i.get('name') == item_name), None)
        if item and item.get('energy_value', 0) > 0:
            base_power = abs(btype.get('base_power', 0))
            overclock = b.get('overclock', 1.0)
            max_power = base_power * overclock
            return max_power * 60 / item['energy_value']
        return 0.0

    recipe_id = b.get('recipe_id')
    if not recipe_id or recipe_id not in recipes_cache:
        return 0.0

    recipe = recipes_cache[recipe_id]
    overclock = b.get('overclock', 1.0)

    for inp in recipe.get('inputs', []):
        if inp['name'] == item_name:
            return inp['per_minute'] * overclock

    return 0.0

def _calc_generator_with_recipe(b, incoming, items_cache, buildings_cache, recipes_cache):
    """Generator with a recipe (e.g. Nuclear Power Plant) — produces waste."""
    # First, calculate as generator
    gen_result = _calc_generator(b, incoming, items_cache, buildings_cache)

    # Then, calculate waste outputs from recipe
    recipe = recipes_cache[b['recipe_id']]
    overclock = b.get('overclock', 1.0)
    efficiency = gen_result.efficiency

    outputs = {}
    for out in recipe.get('outputs', []):
        rate = out['per_minute'] * overclock * efficiency
        outputs[out['name']] = rate

    return CalcResult(
        b['id'], gen_result.building_name,
        efficiency, gen_result.power,
        gen_result.inputs, outputs
    )