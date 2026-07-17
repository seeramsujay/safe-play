# SafePlay - Product Vision & Capabilities

## Product Definition
**SafePlay** is an offline-resilient, decentralized intelligence mesh engineered to monitor crowd safety, mitigate congestion, and coordinate egress logistics within FIFA World Cup 2026 stadiums.

## Problem Statement
During major tournament matches, crowd congestion at exit gates and transit corridors can escalate rapidly into hazardous bottlenecks. When connectivity fails, cloud-based monitoring solutions drop off-line, creating operational blind spots. SafePlay solves this by running localized, grammar-constrained model reasoning at the stadium edge, guaranteeing continuous, sub-second routing decisions and operator control even during severe network brownouts.

## Core Capabilities
1. **Dynamic Spatial Graph Ingestion**: Models vomitories, corridors, concourses, ADA ramps, and transit hubs as nodes and edges.
2. **Cython-Accelerated Pathfinding**: Evaluates crowd flows and computes alternate egress corridors in under 1ms.
3. **Structured SLM/LLM Inference**: Generates schema-compliant, grammar-constrained intervention scripts via Gemini (cloud) or local server (Llama).
4. **Non-Negotiable Operator Control**: Enforces an explicit countdown window (default: 15s) for manual veto before executing automated gate/signage actuation.
5. **GenAI Operations Copilot**: Provides a natural language interface for commanders to query system safety status, accessibility conditions, and transit routes.
6. **Robust Fallbacks**: Cascades automatically from LLM to local semantic fallbacks and rule-based controllers if any latency or parsing bounds are violated.

## User Personas
* **Venue Operations Commander (VOC)**: Monitors stadium-wide safety, approves/vetoes egress rerouting, and queries the Copilot for incident SOPs.
* **Edge Sensors/Turnstiles**: Ingest high-frequency telemetry (density, flow rates) and actuate physical access points or electronic signage boards.

## Non-Negotiables & Tradeoffs
* **Latency Bound**: Time-to-First-Token (TTFT) for inference must be `< 100ms`.
* **Zero Conversational Polish**: The system discards general greeting prompts and conversational filler to preserve operational speed.
* **Safety Lock**: No autonomous actuation is allowed without operator review or explicit panic-mode authorization.
