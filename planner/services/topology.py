"""
Topological sorting for production line calculation.

Builds a directed graph from connections, then sorts buildings
so that every building is processed after all its suppliers.
"""
from collections import defaultdict, deque


class CycleDetectedError(Exception):
    """Raised when a cycle is found in the connection graph."""
    pass


def build_graph(placed_buildings, connections):
    """
    Build a directed graph from connections.

    Args:
        placed_buildings: QuerySet of PlacedBuilding.
        connections: QuerySet of Connection with related port_instances.

    Returns:
        tuple: (graph, in_degree) where:
            graph: {building_id: [dependent_building_ids]}
            in_degree: {building_id: count_of_suppliers}
    """
    building_ids = {pb.id for pb in placed_buildings}
    graph = defaultdict(list)
    in_degree = defaultdict(int)

    # Initialize all buildings
    for b_id in building_ids:
        in_degree[b_id] = 0

    for conn in connections:
        # Only resource connections (belts and pipes) create dependencies
        if conn.connection_type in ('belt', 'pipe'):
            from_id = conn.from_port.placed_building_id
            to_id = conn.to_port.placed_building_id

            if from_id in building_ids and to_id in building_ids:
                graph[from_id].append(to_id)
                in_degree[to_id] += 1

    return dict(graph), dict(in_degree)


def topological_sort(placed_buildings, connections):
    """
    Sort buildings so that suppliers come before consumers.

    Args:
        placed_buildings: QuerySet of PlacedBuilding.
        connections: QuerySet of Connection.

    Returns:
        list: Building IDs in calculation order.

    Raises:
        CycleDetectedError: If a cycle exists in connections.
    """
    graph, in_degree = build_graph(placed_buildings, connections)

    # Start with buildings that have no suppliers
    queue = deque(b_id for b_id, deg in in_degree.items() if deg == 0)
    order = []

    while queue:
        b_id = queue.popleft()
        order.append(b_id)

        for neighbor in graph.get(b_id, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(in_degree):
        raise CycleDetectedError(
            "Обнаружен цикл в соединениях! Проверьте конвейеры и трубы."
        )

    return order
