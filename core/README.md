# Fedora Nova 0.6.4 — Dock Hover & Large Halo Fix

Opravná verze pro Fedora 44 + GNOME Shell 50 a Dash to Dock 105.

## Co opravuje

### Šedý hover v docku

Dash to Dock kreslí vlastní šedý hover přímo na `.overview-icon`.
Fedora Nova 0.6.4 přepisuje přesně tuto vrstvu s vyšší prioritou:

- dock už nemá používat šedý `remark` hover,
- ikona dostane barevný kruh podle aktivního Nova profilu,
- oprava zahrnuje běžné aplikace, focused aplikace i Show Applications,
- background docku je znovu vynucený z barev aktivního profilu.

### Větší hover

Výchozí `circle` je nyní větší:

- app grid: vnější halo 10 px,
- dock: vnější halo 5 px,
- žádný padding ani margin se při hoveru nemění,
- ikona se proto nezmenšuje a neposkakuje,
- vizuálně malé ikonky, například Soubory, dostanou výraznější plochu.

Původní menší varianta zůstává jako:

```bash
fedora-nova hover circle-compact --reload
```

## Instalace / upgrade

```bash
cd "$(xdg-user-dir DOWNLOAD)"
unzip -o fedora-nova-0.6.4.zip
cd fedora-nova-0.6.4
./install.sh
```

Kompletní persistentní setup lze kdykoliv obnovit jedním příkazem:

```bash
fedora-nova preset full --reload
```

Ten zapne User Themes, Dash to Dock, Top Bar All Monitors, Continuous
Squircle, Circle Large hover, Tela Circle + kruhové Steam ikony a Nova barvy
v GTK/libadwaita aplikacích. Zároveň vypne GNOME/Fedora welcome dialog.

Potom aplikuj nový hover explicitně:

```bash
fedora-nova hover none --reload
fedora-nova hover circle --reload
```

Nejjistější je následný relogin.

## Hover režimy

```bash
fedora-nova hover circle --reload
fedora-nova hover circle-compact --reload
fedora-nova hover tile --reload
fedora-nova hover none --reload
fedora-nova hover previous --reload
```

## Folder dialog

Velký SVG superellipse dialog složky z 0.6.2/0.6.3 zůstává beze změny.
