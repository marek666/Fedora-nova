#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
command_exists zenity || die "Chybí zenity. Spusť: sudo dnf install zenity"

profile_picker() {
  local args=()
  while IFS=$'\t' read -r id title description kind; do
    [[ -n "$id" ]] || continue
    [[ "$kind" == custom ]] && title="$title [Forge]"
    args+=("$id" "$title — $description")
  done < <(
    python3 "$SCRIPT_DIR/profile-info.py" list \
      "$NOVA_APP_DIR/config/profiles.json" "$NOVA_CUSTOM_DIR"
  )
  zenity --list --title='Vyber profil' --width=780 --height=520 \
    --column='ID' --column='Profil' "${args[@]}" 2>/dev/null || true
}

while true; do
	  action="$(zenity --list --title='Fedora Nova Control 0.6.4 — Dock Hover Fix' \
	    --width=780 --height=650 --column='Akce' --column='Popis' \
	    'Kompletní setup' 'Persistentní Nova desktop po přihlášení' \
	    'Vypnout uvítání' 'Ztišit GNOME/Fedora welcome dialog' \
	    'Profil' 'Vestavěné i vlastní Forge profily' \
    'Nova Forge' 'Vytvořit profil z libovolné HEX barvy' \
    'Smazat Forge profil' 'Odstranit neaktivní vlastní profil' \
    'Předchozí profil' 'Vrátit poslední změnu profilu' \
    'Dock' 'Compact, Balanced, Showcase nebo Hidden' \
    'Pohyb' 'Reduced, Balanced nebo Smooth — vždy bez blur' \
    'Křivky' 'Classic, Soft, Squircle nebo Ultra' \
    'Hover' 'Circle Large, Circle Compact, Tile nebo None' \
    'GTK aplikace' 'Nova barvy pro Soubory, Textový editor a Nastavení' \
    'Ikony' 'Tela Circle, Steam round, Papirus nebo Adwaita' \
    'Monitory' 'Horní panel na sekundárních monitorech' \
    'Snapshot' 'Vytvořit pojmenovaný bod obnovy' \
    'Obnovit snapshot' 'Vybrat a obnovit dřívější stav' \
    'Export' 'Záloha včetně Forge profilů' \
    'Import' 'Načíst přenosnou zálohu' \
    'Náhled' 'Otevřít lokální přehled profilů' \
    'Stav' 'Zobrazit aktivní nastavení' \
    'Diagnostika' 'Kontrola kompatibility a výkonu' \
    'Reload' 'Znovu načíst Shell theme' \
    'Nouzový režim' 'Vypnout theme a dock' 2>/dev/null || true)"
  [[ -n "$action" ]] || exit 0

	  case "$action" in
	    'Kompletní setup')
	      "$SCRIPT_DIR/apply-preset.sh" full --reload &&
	        zenity --info --text='Kompletní Nova setup byl použit a zapamatován.'
	      ;;
	    'Vypnout uvítání')
	      "$SCRIPT_DIR/disable-welcome.sh" off &&
	        zenity --info --text='Uvítací okna GNOME/Fedora jsou vypnutá.'
	      ;;
	    Profil)
      profile="$(profile_picker)"
      [[ -n "$profile" ]] &&
        "$SCRIPT_DIR/apply-profile.sh" "$profile" --reload &&
        zenity --info --text="Profil $profile byl aplikován."
      ;;
    'Nova Forge')
      name="$(zenity --entry --title='Nova Forge' \
        --text='Název vlastního profilu:' 2>/dev/null || true)"
      [[ -n "$name" ]] || continue
      primary="$(zenity --entry --title='Nova Forge — hlavní barva' \
        --text='Hlavní HEX barva:' --entry-text='#D630F2' 2>/dev/null || true)"
      [[ -n "$primary" ]] || continue
      secondary="$(zenity --entry --title='Nova Forge — vedlejší barva' \
        --text='Vedlejší HEX barva; prázdné pole ji dopočítá automaticky:' \
        --entry-text='#2ED8E8' 2>/dev/null || true)"
      if [[ -n "$secondary" ]]; then
        "$SCRIPT_DIR/forge-profile.sh" "$name" "$primary" "$secondary"
      else
        "$SCRIPT_DIR/forge-profile.sh" "$name" "$primary"
      fi
      ;;
    'Smazat Forge profil')
      mapfile -t custom_rows < <(
        python3 "$SCRIPT_DIR/profile-info.py" list \
          "$NOVA_APP_DIR/config/profiles.json" "$NOVA_CUSTOM_DIR" |
          awk -F '\t' '$4=="custom" {print $1 "\t" $2}'
      )
      ((${#custom_rows[@]})) || {
        zenity --info --text='Nejsou vytvořené žádné Forge profily.'
        continue
      }
      args=()
      for row in "${custom_rows[@]}"; do
        IFS=$'\t' read -r id title <<<"$row"
        args+=("$id" "$title")
      done
      profile="$(zenity --list --title='Smazat Forge profil' \
        --column='ID' --column='Název' "${args[@]}" 2>/dev/null || true)"
      [[ -n "$profile" ]] && "$SCRIPT_DIR/custom-profile.sh" delete "$profile"
      ;;
    'Předchozí profil')
      "$SCRIPT_DIR/rollback-profile.sh" &&
        zenity --info --text='Předchozí profil byl obnoven.'
      ;;
    Dock)
      preset="$(zenity --list --title='Vyber dock' --column='Preset' --column='Popis' \
        compact '36 px' balanced '42 px' showcase '48 px' \
        hidden 'silnější autohide' 2>/dev/null || true)"
      [[ -n "$preset" ]] && "$SCRIPT_DIR/apply-dock.sh" "$preset"
      ;;
    Pohyb)
      preset="$(zenity --list --title='Vyber animace' --column='Preset' --column='Popis' \
        reduced 'minimum animací' balanced 'svižný výchozí stav' \
        smooth 'delší animace bez blur' 2>/dev/null || true)"
      [[ -n "$preset" ]] && "$SCRIPT_DIR/apply-motion.sh" "$preset"
      ;;
    Křivky)
      preset="$(zenity --list --title='Vyber charakter rohů' \
        --column='Preset' --column='Popis' \
        classic 'Původní střídmý radius' \
        soft 'Měkčí rohy bez bubble efektu' \
        squircle 'Výchozí continuous-corner poměr' \
        ultra 'Velmi měkký organický vzhled' 2>/dev/null || true)"
      [[ -n "$preset" ]] && "$SCRIPT_DIR/apply-curve.sh" "$preset" --reload
      ;;
    Hover)
      preset="$(zenity --list --title='Hover ikon' --column='Preset' --column='Popis' \
        circle 'Větší kruh jen pod ikonou' circle-compact 'Menší kruhový hover' tile 'Barevný squircle celé dlaždice' \
        none 'Bez podložky' 2>/dev/null || true)"
      [[ -n "$preset" ]] && "$SCRIPT_DIR/apply-hover.sh" "$preset" --reload
      ;;
    'GTK aplikace')
      preset="$(zenity --list --title='GTK aplikace' --column='Akce' --column='Popis' \
        on 'Zapnout a aktualizovat Nova barvy' off 'Odstranit Nova GTK vrstvu' \
        refresh 'Aktualizovat podle aktivního profilu' 2>/dev/null || true)"
      [[ -n "$preset" ]] && "$SCRIPT_DIR/gtk-theme.sh" "$preset"
      ;;
    Ikony)
      preset="$(zenity --list --title='Vyber ikony' --column='Preset' --column='Popis' \
        tela 'Tela Circle' tela-dark 'Tela Circle Dark' tela-light 'Tela Circle Light' \
        tela-steam 'Tela + kruhové Steam hry' papirus 'Papirus Dark' adwaita 'Stock GNOME' 2>/dev/null || true)"
      [[ -n "$preset" ]] && "$SCRIPT_DIR/apply-icons.sh" "$preset"
      ;;
    Monitory)
      preset="$(zenity --list --title='Panel na monitorech' --column='Akce' --column='Popis' \
        on 'Zapnout panel na sekundárních monitorech' \
        off 'Vypnout panel na sekundárních monitorech' \
        status 'Zobrazit stav' 2>/dev/null || true)"
      [[ -n "$preset" ]] && "$SCRIPT_DIR/monitor-panel.sh" "$preset"
      ;;
    Snapshot)
      name="$(zenity --entry --title='Nový snapshot' \
        --text='Název snapshotu:' 2>/dev/null || true)"
      [[ -n "$name" ]] &&
        "$SCRIPT_DIR/snapshot.sh" create "$name" &&
        zenity --info --text="Snapshot $name byl vytvořen."
      ;;
    'Obnovit snapshot')
      mapfile -t snaps < <("$SCRIPT_DIR/snapshot.sh" list)
      ((${#snaps[@]})) || {
        zenity --info --text='Zatím nejsou žádné snapshoty.'
        continue
      }
      name="$(zenity --list --title='Obnovit snapshot' \
        --column='Snapshot' "${snaps[@]}" 2>/dev/null || true)"
      [[ -n "$name" ]] && "$SCRIPT_DIR/snapshot.sh" restore "$name"
      ;;
    Export)
      file="$(zenity --file-selection --save --confirm-overwrite \
        --title='Export Fedora Nova' \
        --filename="$HOME/Fedora-Nova-export.tar.gz" 2>/dev/null || true)"
      [[ -n "$file" ]] &&
        "$SCRIPT_DIR/export-config.sh" "$file" &&
        zenity --info --text="Export uložen do:\n$file"
      ;;
    Import)
      file="$(zenity --file-selection --title='Import Fedora Nova' \
        --file-filter='tar.gz | *.tar.gz' 2>/dev/null || true)"
      [[ -n "$file" ]] && "$SCRIPT_DIR/import-config.sh" "$file"
      ;;
    Náhled) xdg-open "$NOVA_APP_DIR/preview/index.html" >/dev/null 2>&1 & ;;
    Stav)
      tmp="$(mktemp)"
      "$SCRIPT_DIR/status.sh" >"$tmp"
      zenity --text-info --title='Fedora Nova — stav' \
        --width=800 --height=600 --filename="$tmp" || true
      rm -f "$tmp"
      ;;
    Diagnostika)
      tmp="$(mktemp)"
      "$SCRIPT_DIR/doctor.sh" >"$tmp"
      zenity --text-info --title='Fedora Nova — diagnostika' \
        --width=920 --height=700 --filename="$tmp" || true
      rm -f "$tmp"
      ;;
    Reload)
      "$SCRIPT_DIR/reload-theme.sh"
      zenity --info --text='Reload dokončen.'
      ;;
    'Nouzový režim')
      if zenity --question --text='Opravdu vypnout Fedora Nova theme a dock?'; then
        "$SCRIPT_DIR/nova-safe-mode.sh"
      fi
      ;;
  esac
done
