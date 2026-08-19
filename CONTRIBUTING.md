
# Přispívání do Fedora Nova

## Vývoj UI

```bash
./dev-setup-fedora.sh
./dev-run.sh preview
```

V GNOME Builderu otevři kořen projektu a spusť konfiguraci:

- `io.github.fedoranova.FedoraNova.Devel.json` pro bezpečný Flatpak Preview,
- `Native Host` pro skutečné změny Fedora Nova.

## Responzivní testování

- zmenšuj okno pod 720 sp,
- stiskni `Ctrl+Shift+M` pro Adaptive Preview,
- zkontroluj šířky 360, 480, 720 a 1040 px,
- ověř, že žádný `Adw.ActionRow` nepřetéká.

## Kontroly

```bash
./check.sh
```
