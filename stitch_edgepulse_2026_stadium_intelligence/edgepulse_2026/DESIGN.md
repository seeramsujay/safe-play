---
name: EdgePulse 2026
colors:
  surface: '#faf8ff'
  surface-dim: '#d2d9f4'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3ff'
  surface-container: '#eaedff'
  surface-container-high: '#e2e7ff'
  surface-container-highest: '#dae2fd'
  on-surface: '#131b2e'
  on-surface-variant: '#434655'
  inverse-surface: '#283044'
  inverse-on-surface: '#eef0ff'
  outline: '#737686'
  outline-variant: '#c3c6d7'
  surface-tint: '#0053db'
  primary: '#004ac6'
  on-primary: '#ffffff'
  primary-container: '#2563eb'
  on-primary-container: '#eeefff'
  inverse-primary: '#b4c5ff'
  secondary: '#4b41e1'
  on-secondary: '#ffffff'
  secondary-container: '#645efb'
  on-secondary-container: '#fffbff'
  tertiary: '#006243'
  on-tertiary: '#ffffff'
  tertiary-container: '#007d57'
  on-tertiary-container: '#bdffdc'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b4c5ff'
  on-primary-fixed: '#00174b'
  on-primary-fixed-variant: '#003ea8'
  secondary-fixed: '#e2dfff'
  secondary-fixed-dim: '#c3c0ff'
  on-secondary-fixed: '#0f0069'
  on-secondary-fixed-variant: '#3323cc'
  tertiary-fixed: '#85f8c4'
  tertiary-fixed-dim: '#68dba9'
  on-tertiary-fixed: '#002114'
  on-tertiary-fixed-variant: '#005137'
  background: '#faf8ff'
  on-background: '#131b2e'
  surface-variant: '#dae2fd'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '700'
    lineHeight: '1.1'
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.3'
  headline-sm:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: '1.4'
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.5'
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: '1.4'
    letterSpacing: 0.01em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: '600'
    lineHeight: '1.2'
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 4px
  xs: 0.25rem
  sm: 0.5rem
  md: 1rem
  lg: 1.5rem
  xl: 2rem
  2xl: 3rem
  gutter: 1.5rem
  margin-mobile: 1rem
  margin-desktop: 2rem
---

## Brand & Style
The design system is engineered for high-stakes professional environments where clarity, speed of cognition, and accessibility are paramount. The brand personality is **Professional, Calm, and Optimistic**, balancing a data-dense utility with a clean, airy aesthetic. 

The visual style follows a **Modern Corporate** approach with a focus on high-contrast accessibility (WCAG AAA target). It avoids unnecessary decorative elements, favoring structural integrity and clear informational hierarchy. The emotional response should be one of reliability and quiet confidence, ensuring users feel in control of complex data streams.

## Colors
This design system utilizes a high-contrast palette to ensure maximum legibility. 

- **Primary Action:** Optimistic Blue (#2563EB) is reserved for interactive elements and primary calls to action.
- **Pillars:** Distinct colors are used to categorize core functional areas: Emerald for Safety, Indigo for Security, and Deep Amber for Service.
- **Semantic Logic:** Status indicators must never rely on color alone. Every semantic state is paired with a specific icon:
  - **Success:** Emerald + Circle icon.
  - **Warning:** Amber + Triangle icon.
  - **Critical:** Red + Octagon icon.
- **Contrast Ratios:** All text-on-background combinations must meet or exceed WCAG AA (4.5:1) standards, with primary content targeting AAA (7:1+).

## Typography
The system utilizes **Inter** for its exceptional legibility at small sizes and high x-height. 

- **Scale:** The base body size is set to 14px to support data density without sacrificing readability. 
- **Hierarchy:** Use FontWeight 600 for headings to create a clear "scan-line" for the user's eye. 
- **Accessibility:** Line heights are generous (1.5 - 1.6) for body text to reduce visual crowding. Never use light font weights (300 or less) for critical information.

## Layout & Spacing
The layout uses a **Fluid Grid** system based on an 8px (0.5rem) spatial rhythm.

- **Desktop:** 12-column grid with 24px gutters. Content should be contained within a max-width of 1440px for optimal line lengths.
- **Tablet:** 8-column grid with 20px gutters.
- **Mobile:** 4-column grid with 16px gutters and 16px side margins.
- **Density:** While the system supports data density, use `spacing-lg` (24px) between major sections to provide visual "breathing room," preventing user fatigue during long sessions.

## Elevation & Depth
Depth is communicated through **Tonal Layers** and subtle, low-opacity shadows. 

- **Level 0 (Background):** #FAFAF9 – The canvas.
- **Level 1 (Surface):** #FFFFFF – Default card and container color. Uses a 1px border (#E2E8F0) to define boundaries in high-glare environments.
- **Level 2 (Elevated):** Shallow, soft shadow (0px 2px 4px rgba(15, 23, 42, 0.05)). Used for hover states or active card selections.
- **Level 3 (Overlay):** Moderate shadow (0px 10px 15px rgba(15, 23, 42, 0.1)). Used for modals, dropdowns, and toast notifications to pull them forward in the Z-space.

## Shapes
This design system uses a **Rounded** shape language to soften the "industrial" feel of data-heavy interfaces.

- **Standard Radius:** 0.5rem (8px) for small components like inputs and buttons.
- **Container Radius (rounded-xl):** 0.75rem (12px) for cards, modals, and main content areas.
- **Full Radius:** Reserved exclusively for tags, badges, and circular action buttons (FABs).

## Components
- **Buttons:** Primary buttons use Optimistic Blue backgrounds with White text. Secondary buttons use a Slate Gray outline. Interaction states (hover/focus) must include a 2px offset ring for keyboard navigation visibility.
- **Input Fields:** 14px text, 12px padding. Focus states use a 2px solid Optimistic Blue border. Error states must include the "Critical" octagon icon within the field trailing area.
- **Cards:** White background, 12px corner radius, 1px Slate border (#E2E8F0). No shadow by default; elevation is applied only on interaction.
- **Chips/Badges:** Used for "Pillars." Backgrounds should be 10% opacity of the pillar color, with 100% opacity text for contrast compliance.
- **Data Tables:** Use subtle zebra-striping (#FAFAF9) on every other row. Headers should be Sticky and use a semi-bold weight.
- **Status Indicators:** 
  - *Success:* Circle icon + Emerald text.
  - *Warning:* Triangle icon + Amber text.
  - *Critical:* Octagon icon + Red text.