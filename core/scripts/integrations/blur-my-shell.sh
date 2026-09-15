#!/usr/bin/env bash
set -euo pipefail

INTEGRATION_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$INTEGRATION_DIR/../lib.sh"

ACTION="${1:-apply}"

if [[ $# -gt 1 ]]; then
    warn "Použij: $0 [status|apply|restore]"
    exit 2
fi

case "$ACTION" in
    status|apply|restore)
        ;;
    *)
        warn "Neznámý příkaz: $ACTION. Použij status, apply nebo restore."
        exit 2
        ;;
esac

BMS_UUID="blur-my-shell@aunetx"
BMS_SCHEMA="org.gnome.shell.extensions.blur-my-shell.overview"
BMS_KEY="style-components"
BMS_GSETTINGS=(gsettings)

bms_setting_exists() {
    "${BMS_GSETTINGS[@]}" list-keys "$BMS_SCHEMA" 2>/dev/null |
        grep -Fx "$BMS_KEY" >/dev/null
}

if ! bms_setting_exists; then
    schema_dir="$NOVA_DATA_HOME/gnome-shell/extensions/$BMS_UUID/schemas"

    if [[ -f "$schema_dir/gschemas.compiled" ]]; then
        BMS_GSETTINGS=(gsettings --schemadir "$schema_dir")
    fi
fi

if ! bms_setting_exists; then
    log "Nastavení Blur My Shell není dostupné, integraci přeskakuji."
    exit 0
fi

current="$("${BMS_GSETTINGS[@]}" get "$BMS_SCHEMA" "$BMS_KEY")"
backup_dir="$NOVA_CONFIG_DIR/integrations/blur-my-shell"
backup_file="$backup_dir/previous-style-components"

if [[ "$ACTION" == "status" ]]; then
    log "Aktuální style-components: $current"
    log "Soubor zálohy: $backup_file"

    if [[ -f "$backup_file" ]]; then
        saved="$(cat "$backup_file")"
        log "Zálohovaná původní hodnota: $saved"
    else
        log "Záloha zatím neexistuje."
    fi

    exit 0
fi

writable="$("${BMS_GSETTINGS[@]}" writable "$BMS_SCHEMA" "$BMS_KEY")"

if [[ "$writable" != true ]]; then
    warn "Nastavení Blur My Shell není zapisovatelné."
    exit 1
fi

if [[ "$ACTION" == "restore" ]]; then
    if [[ ! -e "$backup_file" ]]; then
        log "Záloha neexistuje, není co obnovovat."
        exit 0
    fi

    if [[ ! -f "$backup_file" || ! -r "$backup_file" ]]; then
        warn "Záloha není čitelný soubor. Obnovu ruším."
        exit 1
    fi

    saved="$(cat "$backup_file")"

    case "$saved" in
        0|1|2|3)
            ;;
        *)
            warn "Záloha obsahuje neplatnou hodnotu. Ponechávám ji beze změn."
            exit 1
            ;;
    esac

    if [[ "$current" != "0" && "$current" != "$saved" ]]; then
        warn "Aktuální hodnota je $current, záloha obsahuje $saved."
        warn "Nastavení mohlo být ručně změněno. Nic nepřepisuji a zálohu ponechávám."
        exit 1
    fi

    if [[ "$current" != "$saved" ]]; then
        "${BMS_GSETTINGS[@]}" set "$BMS_SCHEMA" "$BMS_KEY" "$saved"
    fi

    actual="$("${BMS_GSETTINGS[@]}" get "$BMS_SCHEMA" "$BMS_KEY")"

    if [[ "$actual" != "$saved" ]]; then
        warn "Obnova nebyla potvrzena. Zálohu ponechávám."
        exit 1
    fi

    rm -- "$backup_file"
    log "Obnovena původní hodnota: $actual. Záloha byla odstraněna."
    exit 0
fi

mkdir -p "$backup_dir"

if [[ ! -e "$backup_file" ]]; then
    printf '%s\n' "$current" > "$backup_file"
    log "Uložena původní hodnota: $current"
else
    log "Záloha už existuje, ponechávám ji."
fi

if [[ "$current" != "0" ]]; then
    "${BMS_GSETTINGS[@]}" set "$BMS_SCHEMA" "$BMS_KEY" 0
    log "Stylování přehledu v Blur My Shell vypnuto."
else
    log "Hodnota už je 0, není potřeba ji měnit."
fi

actual="$("${BMS_GSETTINGS[@]}" get "$BMS_SCHEMA" "$BMS_KEY")"

if [[ "$actual" == "0" ]]; then
    log "Kontrola OK: style-components = 0"
else
    warn "Kontrola selhala: očekávám 0, ale hodnota je $actual"
    exit 1
fi