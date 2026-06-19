from collections import defaultdict
from dataclasses import dataclass, field

from .constants import (
    BELT_SPEEDS,
    PIPE_SPEEDS,
    OVERCLOCK_EXPONENT,
    IDLE_POWER_FRACTION,
    PURITY_MULTIPLIERS,
    SOMERSLOOP_OUTPUT_MULTIPLIER,
    SOMERSLOOP_POWER_MULTIPLIER,
)
from .topology import topological_sort
from ..models import Item

@dataclass
class PortFlow:
    """Flow data for one port during calculation."""
    port_instance_id: int
    item_id: int
    rate: float


@dataclass
class BuildingResult:
    """Calculation result for one placed building."""
    placed_building_id: int
    efficiency: float
    power_consumed: float
    inputs: dict
    outputs: dict


@dataclass
class LineResult:
    """Complete calculation result for a production line."""
    building_results: dict = field(default_factory=dict)
    receiver_outputs: dict = field(default_factory=dict)
    total_consumption: float = 0.0
    total_generation: float = 0.0
    total_buildings: int = 0
    errors: list = field(default_factory=list)

    @property
    def net_balance(self):
        return self.total_generation - self.total_consumption


def calculate_line(placed_buildings, connections):
    """Main entry point."""
    pb_map = _index_buildings(placed_buildings)
    conn_map = _index_connections(connections)

    try:
        order = topological_sort(placed_buildings, connections)
    except Exception as e:
        return LineResult(errors=[str(e)])

    incoming = defaultdict(lambda: defaultdict(float))
    building_results = {}
    receiver_outputs = defaultdict(float)
    total_consumption = 0.0
    total_generation = 0.0

    # Check for pressurizer for well extractors
    has_pressurizer = any(
        'Нагнетатель' in pb_map[bid].building_type.name
        for bid in pb_map
    )

    for b_id in order:
        pb = pb_map[b_id]
        result = _calculate_building(pb, incoming, conn_map, has_pressurizer)
        building_results[b_id] = result

        if pb.building_type.category == 'storage' and 'Приёмник' in pb.building_type.name:
            for port_id, rates in incoming[b_id].items():
                for item_id, rate in rates.items():
                    receiver_outputs[item_id] += rate
        elif pb.building_type.category == 'energy' and pb.building_type.base_power < 0:
            total_generation += abs(result.power_consumed)
        else:
            total_consumption += result.power_consumed

        _propagate_outputs(pb, result, conn_map, incoming)

    return LineResult(
        building_results=building_results,
        receiver_outputs=dict(receiver_outputs),
        total_consumption=total_consumption,
        total_generation=total_generation,
        total_buildings=len(pb_map),
    )


def _index_buildings(placed_buildings):
    return {pb.id: pb for pb in placed_buildings}


def _index_connections(connections):
    result = {'from': defaultdict(list), 'to': defaultdict(list)}
    for conn in connections:
        conn_data = {
            'id': conn.id,
            'type': conn.connection_type,
            'belt_level': conn.belt_level,
            'pipe_level': conn.pipe_level,
            'from_port_id': conn.from_port_id,
            'to_port_id': conn.to_port_id,
        }
        result['from'][conn.from_port_id].append((conn.to_port_id, conn_data))
        result['to'][conn.to_port_id].append((conn.from_port_id, conn_data))
    return result


def _calculate_building(pb, incoming, conn_map, has_pressurizer):
    bt = pb.building_type

    if pb.is_external_input and pb.external_item:
        return BuildingResult(
            placed_building_id=pb.id,
            efficiency=1.0,
            power_consumed=0.0,
            inputs={},
            outputs={_find_output_port(pb, pb.external_item): pb.external_rate or 0},
        )

    if pb.resource_purity is not None:
        return _calculate_extractor(pb, has_pressurizer)

    if bt.category == 'storage' and 'Приёмник' in bt.name:
        return BuildingResult(pb.id, 1.0, 1.0, {}, {})

    if bt.category == 'energy' and bt.base_power < 0:
        return _calculate_power_generator(pb, incoming)

    if 'Разветвитель' in bt.name:
        return _calculate_splitter(pb, incoming, conn_map)

    if 'Слияние' in bt.name:
        return _calculate_merger(pb, incoming)

    if pb.recipe:
        return _calculate_production(pb, incoming)

    return BuildingResult(pb.id, 0.0, 0.0, {}, {})


def _find_output_port(pb, item):
    for pi in pb.port_instances.select_related('building_port').all():
        if pi.building_port.direction == 'output':
            if (pi.building_port.accepted_form == 'liquid') == item.is_liquid:
                return pi.id
    return None


def _calculate_extractor(pb, has_pressurizer):
    """Calculate extractor output. Water extractors have fixed 120/min."""
    if not pb.resource_item or not pb.resource_item.extraction_rate:
        return BuildingResult(pb.id, 0.0, 0.0, {}, {})

    # Well extractors need pressurizer
    if 'Экстрактор скважины' in pb.building_type.name and not has_pressurizer:
        return BuildingResult(pb.id, 0.0, 0.0, {}, {})

    # Water Extractors (lakes) have fixed rate, no purity
    if 'Экстрактор воды' in pb.building_type.name or 'WaterPump' in pb.building_type.name:
        rate = 120.0 * pb.overclock
    else:
        base_rate = pb.resource_item.extraction_rate
        purity_mult = PURITY_MULTIPLIERS.get(pb.resource_purity, 1.0)
        rate = base_rate * purity_mult * pb.overclock

    output_port = pb.port_instances.filter(
        building_port__direction='output',
        item=pb.resource_item,
    ).first()

    power = pb.building_type.base_power * (pb.overclock ** OVERCLOCK_EXPONENT)

    return BuildingResult(
        placed_building_id=pb.id,
        efficiency=1.0,
        power_consumed=power,
        inputs={},
        outputs={output_port.id: rate} if output_port else {},
    )


def _calculate_power_generator(pb, incoming):
    base_power = abs(pb.building_type.base_power)
    allowed_fuel_ids = set(
        pb.building_type.fuel_types.values_list('item_id', flat=True)
    )

    if not allowed_fuel_ids:
        return BuildingResult(pb.id, 0.0, 0.0, {}, {})

    best_power = 0.0
    consumed_item = None
    consumed_rate = 0.0

    for pi in pb.port_instances.filter(building_port__direction='input'):
        for item_id, rate in incoming.get(pb.id, {}).get(pi.id, {}).items():
            if item_id in allowed_fuel_ids:
                item = Item.objects.get(id=item_id)
                if item.energy_value > 0:
                    power = rate * item.energy_value / 60
                    if power > best_power:
                        best_power = power
                        consumed_item = item_id
                        consumed_rate = rate

    if best_power == 0:
        return BuildingResult(pb.id, 0.0, base_power * IDLE_POWER_FRACTION, {}, {})

    max_power = base_power * pb.overclock
    actual_power = min(best_power, max_power)
    efficiency = actual_power / max_power if max_power > 0 else 0

    return BuildingResult(
        placed_building_id=pb.id,
        efficiency=efficiency,
        power_consumed=-actual_power,
        inputs={consumed_item: consumed_rate} if consumed_item else {},
        outputs={},
    )


def _calculate_splitter(pb, incoming, conn_map):
    config = pb.splitter_config or {}
    in_flows = incoming.get(pb.id, {})

    all_items = defaultdict(float)
    for port_flows in in_flows.values():
        for item_id, rate in port_flows.items():
            all_items[item_id] += rate

    output_ports = list(pb.port_instances.filter(
        building_port__direction='output'
    ).order_by('building_port__label'))

    label_to_port = {}
    for pi in output_ports:
        label = pi.building_port.label or ''
        label_to_port[label] = pi.id

    outputs = defaultdict(float)
    remaining = dict(all_items)

    # Phase 1: specific item filters
    for label, target in config.items():
        port_id = label_to_port.get(label)
        if not port_id:
            continue
        if isinstance(target, int) and target in remaining:
            outputs[port_id] = remaining.pop(target)

    # Phase 2: "any" ports
    any_labels = [l for l, t in config.items() if t == 'any']
    if any_labels and remaining:
        total_remaining = sum(remaining.values())
        share = total_remaining / len(any_labels)
        for label in any_labels:
            port_id = label_to_port.get(label)
            if port_id:
                outputs[port_id] = share

    # Phase 3: "overflow" port
    overflow_label = next((l for l, t in config.items() if t == 'overflow'), None)
    if overflow_label and remaining:
        port_id = label_to_port.get(overflow_label)
        if port_id:
            outputs[port_id] = sum(remaining.values())

    return BuildingResult(pb.id, 1.0, 0.0, dict(all_items), dict(outputs))


def _calculate_merger(pb, incoming):
    in_flows = incoming.get(pb.id, {})
    total = defaultdict(float)
    for port_flows in in_flows.values():
        for item_id, rate in port_flows.items():
            total[item_id] += rate

    output_port = pb.port_instances.filter(
        building_port__direction='output'
    ).first()

    return BuildingResult(
        pb.id, 1.0, 0.0,
        dict(total),
        {output_port.id: sum(total.values())} if output_port else {},
    )


def _calculate_production(pb, incoming):
    recipe = pb.recipe
    if not recipe:
        return BuildingResult(pb.id, 0.0, 0.0, {}, {})

    base_power = recipe.max_power if recipe.max_power > 0 else pb.building_type.base_power
    input_reqs = list(recipe.requirements.filter(direction='input'))
    output_reqs = list(recipe.requirements.filter(direction='output'))

    efficiency = 1.0
    consumed = {}

    for req in input_reqs:
        required_rate = req.per_minute * pb.overclock
        incoming_rate = 0.0

        for pi in pb.port_instances.filter(
            building_port__direction='input',
            building_port__accepted_form='liquid' if req.item.is_liquid else 'solid',
        ):
            port_flows = incoming.get(pb.id, {}).get(pi.id, {})
            incoming_rate += port_flows.get(req.item_id, 0)

        if required_rate > 0:
            eff = incoming_rate / required_rate
            efficiency = min(efficiency, eff)
            consumed[req.item_id] = incoming_rate

    outputs = {}
    if efficiency > 0:
        for req in output_reqs:
            output_rate = req.per_minute * pb.overclock * efficiency
            if pb.somersloop_active:
                output_rate *= SOMERSLOOP_OUTPUT_MULTIPLIER
            for pi in pb.port_instances.filter(
                building_port__direction='output',
                building_port__accepted_form='liquid' if req.item.is_liquid else 'solid',
            ):
                if not pi.item or pi.item_id == req.item_id:
                    outputs[pi.id] = output_rate
                    break

        power = base_power * (pb.overclock ** OVERCLOCK_EXPONENT) * efficiency
        if pb.somersloop_active:
            power *= SOMERSLOOP_POWER_MULTIPLIER
    else:
        power = base_power * IDLE_POWER_FRACTION

    return BuildingResult(
        placed_building_id=pb.id,
        efficiency=efficiency,
        power_consumed=power,
        inputs=consumed,
        outputs=outputs,
    )


def _propagate_outputs(pb, result, conn_map, incoming):
    for port_id, rate in result.outputs.items():
        if rate <= 0:
            continue

        connections_out = conn_map['from'].get(port_id, [])
        if not connections_out:
            continue

        share = rate / len(connections_out)

        for to_port_id, conn_data in connections_out:
            if conn_data['type'] == 'belt':
                limit = BELT_SPEEDS.get(conn_data['belt_level'] or 1, 60)
            elif conn_data['type'] == 'pipe':
                limit = PIPE_SPEEDS.get(conn_data['pipe_level'] or 1, 300)
            else:
                continue

            sent = min(share, limit)

            pi = pb.port_instances.filter(id=port_id).select_related('item').first()
            if pi and pi.item:
                incoming[conn_data['to_port_id']][pi.item_id] = (
                    incoming[conn_data['to_port_id']].get(pi.item_id, 0) + sent
                )
