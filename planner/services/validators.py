"""
Validation rules for production lines.
"""
from collections import defaultdict

from django.core.exceptions import ValidationError

from .constants import POWER_POLE_SLOTS


def validate_connections(placed_buildings, connections):
    """
    Validate all connections in a production line.

    Checks:
    - No direct connection from generator/extractor to receiver.
    - Belt/pipe type matches resource form (solid/liquid).
    - Output ports only connect to input ports.
    - Waste output ports must be connected.
    - Power pole slot limits.
    """
    # Build lookup for quick access
    building_map = {pb.id: pb for pb in placed_buildings}

    _validate_no_direct_to_receiver(connections, building_map)
    _validate_connection_form_match(connections)
    _validate_port_directions(connections)
    _validate_waste_connected(placed_buildings, connections)
    _validate_power_pole_slots(placed_buildings, connections)
    validate_well_connections(placed_buildings, connections)


def _validate_no_direct_to_receiver(connections, building_map):
    """Generators and extractors cannot connect directly to receivers."""
    for conn in connections:
        if conn.connection_type not in ('belt', 'pipe'):
            continue

        from_pb = building_map.get(conn.from_port.placed_building_id)
        to_pb = building_map.get(conn.to_port.placed_building_id)

        if not from_pb or not to_pb:
            continue

        from_is_source = (
            from_pb.is_external_input or
            from_pb.resource_purity is not None
        )
        to_is_receiver = (
            to_pb.building_type.category == 'storage' and
            'Приёмник' in to_pb.building_type.name
        )

        if from_is_source and to_is_receiver:
            raise ValidationError(
                'Нельзя подключить генератор или буровую напрямую к Приёмнику. '
                'Добавьте между ними хотя бы одно производственное здание.'
            )


def _validate_connection_form_match(connections):
    """Belt for solid, pipe for liquid."""
    for conn in connections:
        if conn.connection_type not in ('belt', 'pipe'):
            continue

        for port in (conn.from_port, conn.to_port):
            item = port.item
            if not item:
                continue

            if conn.connection_type == 'belt' and item.is_liquid:
                raise ValidationError(
                    f'Нельзя транспортировать жидкость "{item.name}" по конвейеру. '
                    f'Используйте трубу.'
                )
            if conn.connection_type == 'pipe' and not item.is_liquid:
                raise ValidationError(
                    f'Нельзя транспортировать твёрдый ресурс "{item.name}" по трубе. '
                    f'Используйте конвейер.'
                )


def _validate_port_directions(connections):
    """Output ports connect to input ports only."""
    for conn in connections:
        if conn.connection_type not in ('belt', 'pipe'):
            continue

        if conn.from_port.direction != 'output':
            raise ValidationError(
                f'Порт "{conn.from_port}" не является выходным. '
                f'Нельзя начинать соединение с входного порта.'
            )
        if conn.to_port.direction != 'input':
            raise ValidationError(
                f'Порт "{conn.to_port}" не является входным. '
                f'Нельзя заканчивать соединение на выходном порте.'
            )


def _validate_waste_connected(placed_buildings, connections):
    """All waste output ports must have at least one connection."""
    connected_ports = set()
    for conn in connections:
        if conn.connection_type in ('belt', 'pipe'):
            connected_ports.add(conn.from_port_id)

    for pb in placed_buildings:
        if not pb.recipe:
            continue

        waste_reqs = pb.recipe.requirements.filter(
            direction='output', is_waste=True
        )
        if not waste_reqs.exists():
            continue

        for port_instance in pb.port_instances.filter(
            building_port__direction='output'
        ):
            if port_instance.item and waste_reqs.filter(
                item=port_instance.item
            ).exists():
                if port_instance.id not in connected_ports:
                    raise ValidationError(
                        f'Побочный продукт "{port_instance.item.name}" '
                        f'в здании "{pb}" должен быть подключён к конвейеру или трубе.'
                    )

def validate_power_network(placed_buildings, connections):
    """
    Verify all power consumers and generators are connected to the grid.
    """
    powered = set()
    for conn in connections:
        if conn.connection_type == 'power':
            powered.add(conn.from_port.placed_building_id)
            powered.add(conn.to_port.placed_building_id)

    for pb in placed_buildings:
        needs_power = (
            pb.building_type.base_power > 0 or
            pb.building_type.category == 'energy'
        )
        if needs_power and pb.id not in powered:
            raise ValidationError(
                f'Здание "{pb.building_type.name}" требует подключения к энергосети.'
            )

def _validate_power_pole_slots(placed_buildings, connections, mma_enabled=False):
    power_conn_count = defaultdict(int)
    for conn in connections:
        if conn.connection_type == 'power':
            power_conn_count[conn.from_port.placed_building_id] += 1
            power_conn_count[conn.to_port.placed_building_id] += 1

    for pb in placed_buildings:
        bt = pb.building_type
        max_slots = bt.connection_slots

        if mma_enabled and bt.category in ('production', 'energy') and max_slots > 0:
            max_slots += 1

        used = power_conn_count.get(pb.id, 0)
        if max_slots > 0 and used > max_slots:
            raise ValidationError(f'У "{bt.name}" занято {used} из {max_slots} слотов. ')


def validate_well_connections(placed_buildings, connections):
    """Каждый экстрактор скважины должен быть соединён с нагнетателем."""
    pressurizers = {
        pb.id for pb in placed_buildings
        if 'Нагнетатель' in pb.building_type.name
    }
    extractors = {
        pb.id for pb in placed_buildings
        if 'Экстрактор скважины' in pb.building_type.name
    }

    if not pressurizers and not extractors:
        return

    if extractors and not pressurizers:
        raise ValidationError(
            'Экстрактор скважины требует Нагнетатель давления в линии.'
        )

    for ext_id in extractors:
        connected = any(
            (conn.from_port.placed_building_id == ext_id and conn.to_port.placed_building_id in pressurizers) or
            (conn.to_port.placed_building_id == ext_id and conn.from_port.placed_building_id in pressurizers)
            for conn in connections
            if conn.connection_type == 'well'
        )
        if not connected:
            raise ValidationError(
                'Экстрактор скважины должен быть соединён с Нагнетателем '
                'давления скважинным соединением.'
            )