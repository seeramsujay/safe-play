# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False

def get_alternative_route_cy(dict nodes_dict, dict adjacency_dict, str overloaded_zone):
    """
    Cython-optimized alternative route lookup.
    """
    if nodes_dict is None or adjacency_dict is None or overloaded_zone is None:
        return None
    if overloaded_zone not in adjacency_dict:
        return None

    cdef dict targets = adjacency_dict[overloaded_zone]
    cdef str target
    cdef str best_target = None
    cdef double max_spare_capacity = -1.0
    cdef double node_capacity
    cdef double node_density
    cdef double spare_capacity

    for target in targets:
        if target in nodes_dict:
            node_obj = nodes_dict[target]
            node_capacity = node_obj.capacity
            node_density = node_obj.current_density
            if node_density < node_capacity:
                spare_capacity = node_capacity - node_density
                if spare_capacity > max_spare_capacity:
                    max_spare_capacity = spare_capacity
                    best_target = target

    return best_target
