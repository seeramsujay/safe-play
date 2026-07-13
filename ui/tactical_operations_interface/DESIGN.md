---
name: Tactical Operations Interface
colors:
  surface: '#10131a'
  surface-dim: '#10131a'
  surface-bright: '#363941'
  surface-container-lowest: '#0b0e15'
  surface-container-low: '#191b23'
  surface-container: '#1d2027'
  surface-container-high: '#272a31'
  surface-container-highest: '#32353c'
  on-surface: '#e1e2ec'
  on-surface-variant: '#c2c6d6'
  inverse-surface: '#e1e2ec'
  inverse-on-surface: '#2e3038'
  outline: '#8c909f'
  outline-variant: '#424754'
  surface-tint: '#adc6ff'
  primary: '#adc6ff'
  on-primary: '#002e6a'
  primary-container: '#4d8eff'
  on-primary-container: '#00285d'
  inverse-primary: '#005ac2'
  secondary: '#b7c8e1'
  on-secondary: '#213145'
  secondary-container: '#3a4a5f'
  on-secondary-container: '#a9bad3'
  tertiary: '#ffb786'
  on-tertiary: '#502400'
  tertiary-container: '#df7412'
  on-tertiary-container: '#461f00'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#d8e2ff'
  primary-fixed-dim: '#adc6ff'
  on-primary-fixed: '#001a42'
  on-primary-fixed-variant: '#004395'
  secondary-fixed: '#d3e4fe'
  secondary-fixed-dim: '#b7c8e1'
  on-secondary-fixed: '#0b1c30'
  on-secondary-fixed-variant: '#38485d'
  tertiary-fixed: '#ffdcc6'
  tertiary-fixed-dim: '#ffb786'
  on-tertiary-fixed: '#311400'
  on-tertiary-fixed-variant: '#723600'
  background: '#10131a'
  on-background: '#e1e2ec'
  surface-variant: '#32353c'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-sm:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  data-lg:
    fontFamily: JetBrains Mono
    fontSize: 18px
    fontWeight: '500'
    lineHeight: 24px
  data-md:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
  data-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  label-caps:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.1em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  gutter: 12px
  margin: 16px
---

## Brand & Style
This design system is engineered for high-stakes, 24/7 stadium operations environments. The brand personality is authoritative, precise, and mission-critical. It prioritizes rapid information processing and reduced cognitive load during high-pressure events.

The aesthetic follows a **High-Contrast / Modern** approach with a "Command & Control" ethos. It utilizes deep backgrounds to minimize eye strain in dark control rooms, while leveraging vibrant, functional color accents to signal status. The interface feels robust and technical, favoring data density and legibility over decorative elements.

## Colors
The palette is rooted in a deep black base to ensure maximum contrast for status indicators. 
- **Core Neutral:** The primary background is a rich black, with slate grays used for structural partitioning and secondary surfaces.
- **Functional Accents:** Colors are strictly semantic. Use Critical Red only for immediate threats or failures, Warning Amber for preemptive alerts, and Success Green for cleared statuses.
- **Active States:** Subtle glows using the `info_hex` or `primary_color_hex` should be applied to indicate active selections or focused data streams, simulating the look of a self-illuminated tactical display.

## Typography
Legibility is the absolute priority. 
- **Primary Interface:** Inter is used for all UI labels, navigation, and general content to ensure high readability.
- **Technical Data:** JetBrains Mono is utilized for all real-time telemetry, timestamps, coordinates, and numeric values. The monospaced nature ensures that fluctuating data points do not cause "jitter" in the layout.
- **Visual Hierarchy:** Use `label-caps` for section headers within panels to create clear visual anchors. Large display sizes are reserved for critical metrics (e.g., current attendance or emergency countdowns).

## Layout & Spacing
The layout follows a **Fixed Grid** system designed for 1080p and 4K monitoring walls. It utilizes a high-density 12-column grid.
- **Density:** Information density is high. Use the 4px base unit to maintain tight, organized groupings of data.
- **Reflow:** On mobile/tablet (field officer view), the grid collapses to a single column, but data tables maintain horizontal scrolling to preserve monospaced alignment.
- **Panels:** Use standard 12px gutters between dashboard widgets. Internal widget padding should be 16px to keep content from feeling claustrophobic despite the high density.

## Elevation & Depth
In this system, depth is communicated through **Tonal Layers** and **Low-contrast Outlines** rather than traditional shadows, which can look muddy on dark displays.
- **Surface Tiers:** The base level is #09090b. Floating panels or widgets use #1e293b.
- **Borders:** Every interactive element or container must have a 1px solid border (#334155).
- **Interactive Glow:** For active alerts or selected items, use a 0px blur, 2px spread "border-glow" using the semantic color of the status. This creates a technical "screen-on-screen" effect.

## Shapes
The shape language is "Soft" (0.25rem), leaning toward a more rigid, industrial feel. 
- **Sharpness:** Avoid large radii. A small 4px radius is sufficient to prevent the UI from feeling aggressive while maintaining a professional, engineered look.
- **Buttons/Inputs:** Use the 4px standard. 
- **Status Indicators:** Small circular pips (full rounding) are acceptable for status lights only.

## Components
- **Buttons:** Solid slate-gray backgrounds with high-contrast text. Primary actions use the Info Blue. For critical "Trigger" actions (e.g., Alarm), use a ghost-button style with a thick red border that fills on hover.
- **Data Cards:** Must feature a top-aligned "Status Bar" (2px thick) that changes color based on the health of the monitored system.
- **Input Fields:** Darker than the surface tier (#0f172a) with a subtle slate border. Focus states should trigger an Info Blue glow.
- **Chips/Status Badges:** Use JetBrains Mono in all-caps. Backgrounds should be low-opacity versions of the semantic color (e.g., 15% opacity Red) with a 100% opacity text color.
- **Telemetry Sparklines:** Minimalist, no-axis line charts used within lists to show 5-minute trends for power, crowd density, or network load.
- **Gantt/Timeline:** Used for event scheduling; markers should be needle-thin to maintain precision.