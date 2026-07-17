# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False

"""
Cython-Accelerated Routing Module for SafePlay.

Provides highly efficient, static-typed spatial graph traversal routines to calculate
alternative egress routes under sub-millisecond real-time latency constraints.
"""

def get_alternative_route_cy(dict nodes_dict, dict adjacency_dict, str overloaded_zone) -> object:
    """
    Finds the adjacent zone with the highest spare capacity using optimized C loops.
    
    Compiler Directives:
        - boundscheck=False: Disables index bounds checking to maximize loop execution speed.
        - wraparound=False: Disables negative index wrapping support for performance.
        
    Args:
        nodes_dict: Dictionary mapping zone ID keys to SpatialNode objects.
        adjacency_dict: Adjacency dictionary mapping source zones to dictionaries of target edges.
        overloaded_zone: The key identifier of the quadrant exhibiting elevated densities.
        
    Returns:
        The zone ID of the adjacent neighbor exhibiting the highest spare capacity,
        or None if no suitable candidates are available.
    """
    # Defensive checks to handle null/empty parameter inputs safely
    if nodes_dict is None or adjacency_dict is None or overloaded_zone is None:
        return None
    if overloaded_zone not in adjacency_dict:
        return None

    # Static C-type declarations for high-performance variable bindings
    cdef dict targets = adjacency_dict[overloaded_zone]
    cdef str target
    cdef str best_target = None
    cdef double max_spare_capacity = -1.0
    cdef double node_capacity
    cdef double node_density
    cdef double spare_capacity

    # Traverse adjacent target zones within the C loop
    for target in targets:
        if target in nodes_dict:
            # Query node object reference from the nodes lookup dictionary
            node_obj = nodes_dict[target]
            node_capacity = node_obj.capacity
            node_density = node_obj.current_density
            
            # Identify candidate zones with remaining spare capacity
            if node_density < node_capacity:
                spare_capacity = node_capacity - node_density
                
                # Perform linear comparison to select the zone with the maximum spare capacity
                if spare_capacity > max_spare_capacity:
                    max_spare_capacity = spare_capacity
                    best_target = target

    return best_target
