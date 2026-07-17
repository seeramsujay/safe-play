# SafePlay - Product & Communication Guidelines

This document details the branding guidelines, system terminology, and error communication protocols for SafePlay.

## Terminology & Glossary

* **Vomitory**: The exit/entrance corridors connecting the seating bowl to the main concourses.
* **Corridor**: A directed pathway connecting nodes in the stadium's spatial graph.
* **Gate / Portal**: Physical boundary access controls (e.g., Gate A, Gate B).
* **Transit Hub**: Stadium-associated public transit targets (Metro, Shuttle Bus).
* **Intervention Script**: A structured JSON block proposing gate actions and signage changes.
* **Veto Window**: The 15-second grace period during which an operator can cancel a proposed intervention.
* **Operator Override**: Manual actuation or approval bypassing the veto window.
* **System Panic Mode**: The emergency override state which forces all gate actuators open.

## Communication & Interface Tone

* **Operational & Direct**: Eliminate conversational fluff, greetings, and pleasantries. Command panel logs and Copilot answers should be concise, high-contrast, and action-oriented.
* **Multilingual Standard**: All emergency electronic announcements and displays must render simultaneously in **English**, **Spanish**, and **French** to meet FIFA event standards.
* **Accessibility Alerting**: Clearly flag ADA capacity warnings and direct wheelchair/mobility assistance paths to designated nodes (e.g., Gate C North ADA).

## Error Convention & Log Standards

* **Failsafe Visual Cues**: If the connection to the MQTT broker or the LLM fails, clearly mark the dashboard indicators in high-contrast red warning panels.
* **Explicit Exception Messaging**: System API errors must report JSON structured details indicating exactly which validation constraints or bounds were violated.
