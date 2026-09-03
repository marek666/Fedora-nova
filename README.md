# Fedora Nova 0.7.2-dev — Builder + Real GNOME Shell Preview

Tato vývojová verze odděluje dva různé preview režimy:

## 1. Settings Preview

GNOME Builder / Flatpak spouští naši GTK4/libadwaita Settings aplikaci.
Je ideální pro:

- responzivitu,
- navigaci,
- widgety,
- dialogy,
- stavové stránky.

Sám o sobě ale neobsahuje GNOME Shell, takže v něm Shell theme není vidět.

## 2. GNOME Shell Preview

Fedora Nova 0.7.2 přidává skutečný nested GNOME Shell přes Mutter
Development Kit:

```bash
fedora-nova-shell-preview tech
fedora-nova-shell-preview --watch tech
fedora-nova-shell-preview --stop
```

Otevře se **Mutter Development Kit** s vlastním GNOME Shellem v okně.
Preview používá:

- vlastní izolovaný dconf,
- vlastní `XDG_CONFIG_HOME`,
- vlastní kopii Fedora Nova themes,
- vybraný Nova wallpaper,
- User Themes extension,
- Dash to Dock, pokud je dostupný,
- bundled Top Bar All Monitors,
- Tela Circle ikony,
- Continuous Squircle curve,
- Circle Large hover,
- Nova ikony koše z `core/assets/icons` v Tela Circle,
- Nova GTK/libadwaita barvy v izolovaném preview configu,
- vypnuté GNOME/Fedora uvítání uvnitř izolovaného Mutter profilu.

Normální přihlášené GNOME se tím nepřepíná.

Live režim `--watch` sleduje celou složku `core/`. Při změně zdrojů ukončí
nested Shell, znovu vytvoří izolovaný preview root a spustí nové okno s
aktuálním kódem.
Současně běží vždy jen jedna live instance.

## Instalace vývojových závislostí

```bash
./dev-setup-fedora.sh
```

Nově nainstaluje také:

- `sassc`,
- `inotify-tools`,
- `mutter-devkit`,
- `gnome-shell-extension-user-theme`,
- `gnome-shell-extension-dash-to-dock`.

A vytvoří:

```text
~/.local/bin/fedora-nova-shell-preview
```

## GNOME Builder

V Builderu dál spusť aplikaci přes:

```text
io.github.fedoranova.FedoraNova.Devel.json
```

Potom v aplikaci otevři:

```text
Systém → GNOME Shell Preview
```

Vyber profil a klikni:

```text
Spustit Shell Preview
```

I když Settings aplikace běží jako Flatpak Preview, nested Shell se spouští
na hostiteli přes development bridge.

## Ruční spuštění

```bash
./dev-shell-preview.sh tech
./dev-shell-preview.sh --watch tech
./dev-shell-preview.sh --stop
./dev-shell-preview.sh pulse
./dev-shell-preview.sh midnight
```

Preview zavřeš obyčejným zavřením okna Mutter Development Kit.

## Kompletní systémové nastavení

```bash
fedora-nova preset full --reload
```

Zapne User Themes, Dash to Dock a Top Bar All Monitors, nastaví Continuous
Squircle curve, Circle Large hover, Tela Circle + kruhové Steam ikony, Nova
GTK/libadwaita barvy, session restore po přihlášení a vypne GNOME/Fedora
welcome dialog.

## Kde upravovat theme

```text
core/themes/Fedora-Nova-Tech/gnome-shell/gnome-shell.css
```

V live režimu se nested Shell po změně CSS restartuje automaticky.

Opakovatelné GNOME Shell vrstvy se dají generovat ze Sass zdrojů:

```bash
core/scripts/build-theme-sass.sh --check
core/scripts/build-theme-sass.sh --apply
```

Tailwind pro Shell theme nepoužíváme, protože GNOME Shell není webový DOM.
Release artefaktem zůstává obyčejné CSS.

## Kde upravovat Settings aplikaci

```text
src/fedora_nova/window.py
src/fedora_nova/pages.py
src/fedora_nova/style.css
```
