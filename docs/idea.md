# Idea: safe-play

## The Thing
safe-play is an offline-first, highly decentralized intelligence mesh designed to manage crowd safety and event egress logistics across FIFA World Cup 2026 stadiums. It processes high-frequency edge metrics directly within stadium zones (such as portals, corridors, and perimeter gates) using localized small language models (SLMs). The system interprets structural graphs, spatial densities, and flow patterns to recommend real-time egress interventions.

## The End Result
The system operates as a zero-fluff middleware bridge that connects stadium turnstiles and edge cameras to digital signage and terminal displays used by the Venue Operations Command (VOC). When crowd densities swell past safe operational limits during a major tournament match or emergency egress, the system produces a structured, grammar-constrained JSON intervention script. This script queues up on the operator's panel with an explicit 2-second countdown clock. If the operator does not actively hit "Veto," the system automatically reroutes dynamic stadium signage updates and adjusts gate entry behaviors, logging the entire process to an append-only ledger.

## Why This Matters
Modern crowd catastrophes—like those witnessed during stadium egress bottlenecks—are rarely caused by instantaneous panic; they are structural communication and routing breakdowns occurring during wide-scale network brownouts or system overloads. safe-play guarantees that even if the stadium completely loses its cloud backhaul connection or central core servers go dark, localized infrastructure remains alert, predictive, and safe.

## Acceptable Tradeoffs
* **Conversational Polish**: The system completely discards natural language dialogue, greeting prompts, or pleasantries from the SLMs.
* **Feature Breadth**: General fan engagement features, ticketing, and historical telemetry patterns are entirely out of scope.
* **UI Fluidity**: The management console favors low-overhead text streams and minimal canvas rendering over heavy animations.

## Non-Negotiables
* **Human Sovereignty**: The system must never silently override physical emergency gates or change exit routing parameters without providing an explicit window for an operator veto.
* **Deterministic Contract**: Model outputs must strictly conform to the expected Pydantic schema; any runtime parsing failure triggers an immediate fallback to hardcoded safety rules.
* **Sub-Second Prefill**: Time-to-First-Token (TTFT) calculations must remain below 100 milliseconds using local hardware prompt caching.

## The Mentality (Soul)
You are building software for a high-stress, high-stakes stadium operating environment. When networks fail, radios jam, and thousands of fans crowd a perimeter gate, our code must not hang on a parsing error or freeze waiting for a cloud API request. Every byte must serve a concrete operational goal. If a component cannot fail safely, it has no place in this codebase.
