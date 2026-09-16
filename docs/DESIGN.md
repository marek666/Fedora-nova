# Fedora Nova — Hover design

## Ownership

Fedora Nova owns the visual appearance of hover, focus, selected, active, checked and outlined states. Extensions may provide behavior or effects, but they should not compete with the Fedora Nova theme for those visual states.

Blur My Shell is used for blur effects only. When its overview schema is available, Fedora Nova sets `style-components` to `0` so BMS does not add its own app-grid, search or overview component colors.

Dash to Dock can paint hover state on the outer item, the application actor, or the icon wrapper, so Fedora Nova explicitly clears those wrappers before drawing its own halo.

## Layers

- `.overview-tile` contains the icon area and label and stays visually transparent.
- `.overview-icon` is kept transparent so extension styling cannot add a second background.
- the inner `StBin` gets a nearly transparent base fill because St needs a painted background for reliable `box-shadow` rendering.
- the icon texture and folder miniature remain unpainted by the hover layer.
- the text label is not part of the halo.

## Current circle geometry

- app-grid halo: 7 px secondary-color ring,
- dock halo: 7 px secondary-color ring,
- Show Applications halo: 5 px secondary-color ring.

The halo is rendered with `box-shadow`, so hover does not change icon layout or size.

Application and folder icon wrappers currently use 5 px padding and a 25 px radius. The Show Applications button has its own actor path and therefore its own hover rule.

## Source ownership

The default circle hover is maintained in:

```text
core/themes-src/scss/layers/_hover-circle.scss
```

Preview startup, restart and hot reload build the selected theme from the same staging pipeline. The default `circle` hover remains SCSS-owned; non-default hover modes are applied by the Python runtime renderer when selected.
