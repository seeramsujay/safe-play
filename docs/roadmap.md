# Roadmap: safe-play

## Legend
DONE | ACTIVE | BLOCKED | COLAB | LOCAL | RISK

## Phases

### Phase 1 — Core Core Architecture & Simulation [LOCAL]
**Goal**: Set up async Python skeleton, local MQTT broker, and basic structural schemas.
**Depends**: None

- [ ] Setup project repository with async stubs, Pydantic templates, and local Mosquitto test container.
- [ ] Construct dynamic directed spatial graph matrices $G=(V, E)$ representing physical venue entry vomitories.
- [ ] Implement edge telemetry receiver module handling default QoS 0 streams.

### Phase 2 — GBNF Grammar Optimization & Offloaded Testing [COLAB]
**Goal**: Formulate grammar token state machines and evaluate model parsing under load.
**Depends**: Phase 1

- [ ] Set up Colab notebook environment to build and parse context-free GBNF structures.
- [ ] Generate synthetic multi-camera dataset vectors matching the Wildtrack format to stress-test schema parsers.
- [ ] Evaluate token prefill speeds across Qwen-2.5-7B and Llama-3.1-8B variations.
*Constraint*: MacBook Air 2017 cannot local-test large batch generation loops without immediate memory starvation.
*Colab*: Runs synthetic load testing scripts and returns compliance telemetry logs to Drive.

### Phase 3 — Orchestration & Human-In-The-Loop Guarding [LOCAL]
**Goal**: Finalize the 2-second automated SLA execution loop and operator interception layer.
**Depends**: Phase 2

- [ ] Code the asynchronous verification gateway thread with an interceptible 2-second sleep mechanism.
- [ ] Implement dynamic backpressure rules toggling targeted nodes from QoS 0 up to QoS 1 during crowd surges.
*Risk*: High MQTT packet loss rates if broker TCP buffers overflow during high-frequency telemetry dumps.
- [ ] Write the append-only local audit trail logger saving raw outputs and manual override states.

### Phase 4 — Hardening & Degraded Operational Failbacks [LOCAL]
**Goal**: Guarantee fallback behavior during local server or network dropouts.
**Depends**: Phase 3

- [ ] Deploy static threshold-based rule fallback scripts to bypass the inference engine if the local port loses connection.
- [ ] Add basic mutual TLS (mTLS) stubs and signature validation checks to incoming MQTT sensor payloads.
