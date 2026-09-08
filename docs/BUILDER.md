# GNOME Builder — Fedora Nova 0.7.2-dev

## Proč se pořád zobrazoval Flatpak Preview

To nebyla chyba tvého přepnutí. Builder vidí Flatpak manifest a používá ho jako build/run konfiguraci. Náš původní `.buildconfig` s `runtime=host` nebyl v aktuálním workflow spolehlivý.

Proto ho 0.7.2-dev už nepoužívá.

## Doporučený workflow

Spusť projekt normálně přes:

```text
io.github.fedoranova.FedoraNova.Devel.json
```

Po startu aplikace:

- **Systém → System Host OFF** = bezpečný UI preview,
- **Systém → System Host ON** = skutečné změny hostitelské Fedory.

Builder tak může pořád využívat čisté GNOME 50 SDK a my nemusíme kvůli každému reálnému testu měnit build konfiguraci.

## Host požadavek

Na hostiteli musí fungovat:

```bash
fedora-nova status
```

Aplikace jej z Flatpaku spouští přes `flatpak-spawn --host`.

## Responzivita

`Ctrl+Shift+M` otevře Adaptive Preview. Testuj zejména 360, 480, 720 a 1040 px.


# Skutečný GNOME Shell theme v testovacím okně

Flatpak Preview testuje pouze Settings aplikaci. Pro theme používej
Mutter Development Kit:

```bash
./dev-shell-preview.sh tech
./dev-shell-preview.sh --watch tech
./dev-shell-preview.sh --stop
```

nebo přímo v Settings:

```text
Systém → GNOME Shell Preview → Spustit Shell Preview
Systém → GNOME Shell Preview → Spustit Live Preview
Systém → GNOME Shell Preview → Zastavit Live Preview
```

GNOME 49+ používá:

```bash
dbus-run-session gnome-shell --devkit --wayland
```

Preview má oddělené XDG config/data/cache/state adresáře, takže jeho
GSettings/dconf konfigurace nezasahuje do běžného sezení.

Live Preview sleduje `core/themes`, `core/assets/wallpapers` a
`core/config/profiles.json`. Při změně ukončí nested Shell a spustí nové
izolované okno s aktuální kopií souborů.
Současně běží jen jedna live instance; další kliknutí už nové okno neotevře.

# Sass pro theme vrstvy

Tailwind se pro GNOME Shell theme nepoužívá, protože Shell CSS není webový DOM.
Sass je praktičtější: vygeneruje obyčejné CSS, které lze vydat bez runtime
závislostí.

```bash
core/scripts/build-theme-sass.sh --check
core/scripts/build-theme-sass.sh --generate
core/scripts/build-theme-sass.sh --apply
```

`--apply` synchronizuje jen marker bloky `NOVA_CURVE` a `NOVA_HOVER` ve
stávajících theme CSS souborech.
