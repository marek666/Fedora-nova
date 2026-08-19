# Fedora Nova 0.6.4 — Hover design

## Vrstvy

- `.overview-tile` obsahuje ikonovou oblast i text a zůstává průhledná.
- `.overview-icon` je resetovaná, protože Dash to Dock na ni kreslí šedý hover.
- vnitřní `StBin` dostává barevnou kruhovou podložku.
- text label není součástí podložky.

## Velikosti

### Circle Large

- app grid halo: 10 px,
- dock halo: 5 px,
- vnitřní accent ring: 2 px.

### Circle Compact

- app grid halo: 5 px,
- dock halo: 3 px.

Halo je vykreslené přes `box-shadow`, takže nezmění layout ani velikost ikony.
