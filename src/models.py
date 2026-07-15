import logging
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator

logger = logging.getLogger(__name__)

try:
    from src.routing import get_alternative_route_cy
    HAS_CYTHON = True
except ImportError:
    HAS_CYTHON = False

# TelemetryPayload represents high-frequency metrics from edge turnstiles and cameras
class TelemetryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    zone_id: str = Field(..., min_length=1, max_length=64, description="Unique identifier of the physical stadium quadrant/vomitory")
    crowd_density: float = Field(..., ge=0.0, le=20.0, description="Estimated crowd density in people/m^2")
    flow_rate_in: float = Field(..., ge=0.0, description="Rate of people entering the zone per minute")
    flow_rate_out: float = Field(..., ge=0.0, description="Rate of people exiting the zone per minute")
    timestamp: float = Field(..., gt=0.0, description="Epoch timestamp of telemetry collection")

# InterventionScript is the grammar-constrained schema required from the SLM
_VALID_HAZARD_LEVELS = {"low", "medium", "high", "critical"}
_VALID_GATE_ACTIONS = {"KEEP_OPEN", "SLOW_ENTRY", "CLOSE_IMMEDIATELY", "REVERSE_FLOW"}

class InterventionScript(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    zone_id: str = Field(..., min_length=1, max_length=64, description="The physical stadium quadrant/vomitory identifier")
    hazard_level: str = Field(..., description="Assessed hazard level: 'low', 'medium', 'high', 'critical'")
    action_required: bool = Field(..., description="True if operator must approve signage or gate changes")
    reroute_target: Optional[str] = Field(None, description="Alternative zone_id to redirect crowd flow if action_required is True")
    signage_instruction: str = Field(..., max_length=120, description="Short text to display on dynamic digital signage")
    gate_action: str = Field(..., description="Turnstile/gate control action: 'KEEP_OPEN', 'SLOW_ENTRY', 'CLOSE_IMMEDIATELY', 'REVERSE_FLOW'")
    rationale: str = Field(..., max_length=100, description="Zero-fluff explanation of the assessment (maximum 10 words)")

    @field_validator("hazard_level")
    @classmethod
    def validate_hazard_level(cls, v: str) -> str:
        if v not in _VALID_HAZARD_LEVELS:
            raise ValueError(f"hazard_level must be one of {_VALID_HAZARD_LEVELS}")
        return v

    @field_validator("gate_action")
    @classmethod
    def validate_gate_action(cls, v: str) -> str:
        if v not in _VALID_GATE_ACTIONS:
            raise ValueError(f"gate_action must be one of {_VALID_GATE_ACTIONS}")
        return v

# SpatialGraph representing G = (V, E) of stadium quadrants and entry vomitories
class SpatialNode(BaseModel):
    zone_id: str
    capacity: float  # Max safe capacity
    current_density: float = 0.0

class SpatialEdge(BaseModel):
    source: str
    target: str
    max_flow_rate: float  # Max throughput in people/minute
    current_flow_rate: float = 0.0

class SpatialGraph:
    """
    Represents physical stadium corridors as a directed spatial graph matrix G = (V, E)
    """
    def __init__(self, nodes: List[SpatialNode], edges: List[SpatialEdge]):
        self.nodes: Dict[str, SpatialNode] = {n.zone_id: n for n in nodes}
        self.adjacency: Dict[str, Dict[str, SpatialEdge]] = {n.zone_id: {} for n in nodes}
        for edge in edges:
            if edge.source in self.adjacency and edge.target in self.adjacency:
                self.adjacency[edge.source][edge.target] = edge

    def update_node_density(self, zone_id: str, density: float) -> None:
        if zone_id in self.nodes:
            self.nodes[zone_id].current_density = density

    def update_edge_flow(self, source: str, target: str, flow_rate: float) -> None:
        if source in self.adjacency and target in self.adjacency[source]:
            self.adjacency[source][target].current_flow_rate = flow_rate

    def get_alternative_route(self, overloaded_zone: str) -> Optional[str]:
        """
        Finds adjacent zones with density below capacity limits to reroute flow.
        Prefers the Cython-optimised path; falls back to pure Python on error.
        """
        if HAS_CYTHON:
            try:
                return get_alternative_route_cy(self.nodes, self.adjacency, overloaded_zone)
            except Exception as exc:
                logger.warning("Cython route lookup failed, falling back to pure Python: %s", exc)

        if overloaded_zone not in self.adjacency:
            return None
        
        candidates = []
        for target, edge in self.adjacency[overloaded_zone].items():
            target_node = self.nodes.get(target)
            if target_node and target_node.current_density < target_node.capacity:
                candidates.append((target, target_node.capacity - target_node.current_density))
        
        # Return candidate with the most spare capacity
        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            return candidates[0][0]
        return None
