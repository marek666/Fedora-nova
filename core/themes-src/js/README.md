# SVG pozadí složek v Preview

`squircle.js` řídí vykreslenou velikost SVG pozadí `.app-folder-dialog`.
Zdroj obrázku dál určuje téma: například
`core/themes/Fedora-Nova-Tech/gnome-shell/assets/app-folder-squircle.svg`.
SVG soubor se na disku nepřepisuje; mění se jeho `background-size` a pozice.
Samotné rozměry SVG nemění mřížku ani velikost ikon. Volba `dockGap`
navíc omezuje dostupný prostor celého dialogu nad spodním dockem.

## Nastavení

```js
export const folderBackground = Object.freeze({
    width: '100%',
    height: '100%',
    inset: '0px',
    dockGap: '24px',
});
```

- `%`: procenta skutečné šířky/výšky dialogu, před odečtením insetu.
- `vw`, `vh`: procenta pracovní plochy primárního monitoru (bez panelu).
- `px`: pixely St CSS; adaptér zohledňuje theme scale factor.
- `inset`: minimální vnitřní odstup obrázku od hran dialogu, v každé ose.
  Nejde o padding obsahu. SVG má navíc vlastní průhledný okraj a stín.
- `dockGap`: minimální mezera mezi spodní hranou dialogu a horní hranou
  viditelného pozadí spodního docku. `24px` znamená 24 CSS px; při škálování
  2× jde o 48 souřadnicových pixelů Shellu. `%` zde používá výšku pracovní plochy.

Pro větší odstup změň například `dockGap: '40px'`. Adaptér vyhradí prostor
paddingem obalu dialogu a omezí maximální výšku dialogu. GNOME jej vycentruje
ve zbývajícím prostoru nad dockem; SVG se přizpůsobí nové alokaci. Výpočet
odečítá mezeru od skutečné horní hrany docku, takže jeho výšku neodečte dvakrát,
pokud ji již zohledňuje pracovní plocha.

Podpora je určena pro spodní vodorovný dock primárního monitoru (Dash to Dock
105 i standardní dash). Skrytý dock, horní či svislý dock a dock mimo tento
monitor se ignorují. Při otevřené složce se poloha ověřuje každých 100 ms,
aby se zachytily i posuny při animaci; během animace může změna krátce zaostávat.
Po zavření kontrola skončí, při vypnutí rozšíření se odstraní ihned a styly
se obnoví. Extrémně malé okno nemusí pojmout minimální obsah složky; automatické
testy výpočtu nezaručují čitelnost ikon v takovém okně.

Například `width: '90%'`, `height: '80vh'`, `inset: '12px'` požaduje
90 % šířky dialogu a 80 % výšky pracovní plochy. Výsledek se omezí tak,
aby se vešel do dialogu s odstupem alespoň 12 CSS px, a vycentruje se.
Výchozí `100% × 100%` pokryje celou plochu dialogu SVG plátnem.
Šířka a výška se škálují nezávisle: čtvercové SVG tak může vyplnit obdélník,
ale jeho kontura se tím také protáhne. Nejde o přegenerování tvaru s konstantními
rohy. Menší obrázek rovněž nezmenší obsah složky.

## Jak je to zapojené

1. Preview launcher zkopíruje modul a adaptér z
   `dev-tools/folder-layout-preview/` do izolovaných Preview dat.
2. Adaptér obalí `AppFolderDialog.popup()` přes `InjectionManager`.
3. Při prvním otevření uloží původní inline styl a připojí sledování alokace.
   Dokud dialog nemá skutečné rozměry, nic nepočítá.
4. `calculateFolderBackground()` převede jednotky, omezí rozměry na dialog
   a spočítá souřadnice pro vycentrování.
5. Pro SVG adaptér nastaví `background-size`, `background-position` a
   `background-repeat` s `!important`. Původní `background-image` z tématu
   zůstává platný. Prázdný původní inline styl nesmí vytvořit úvodní středník:
   parser St by celý seznam deklarací odmítl. To ověřuje i test s GJS/St.
6. Změna alokace, monitorů, pracovní plochy nebo škálování výpočet zopakuje.
   Shodný styl se podruhé nezapisuje, aby nevznikla smyčka přepočtů.
7. `calculateDockClearance()` spočítá horní a spodní odsazení obalu a maximální
   výšku dialogu. Bez viditelného spodního docku se obnoví původní omezení.
8. Vypnutí rozšíření obnoví původní styly i metodu, odpojí signály a zruší časovač.

Pro nové hlavní verze GNOME je potřeba znovu ověřit interní `_viewBox`.
Metadata zatím povolují GNOME Shell 50. Host instalace se nemění.

## Spuštění a ověření

```bash
./dev-shell-preview.sh --stop
./dev-shell-preview.sh --watch tech
```

Launcher při každém startu zapne experimentální rozšíření. Změna JS ve watch
vyvolá plný restart Preview. Otevři složku v přehledu aplikací a ověř,
že SVG sleduje její rozměry. Vyzkoušej jinou velikost Preview i škálování.
Automatické testy ověřují výpočty, napojení a obnovu stylu; vizuální kontrola
je stále potřeba pro posouzení kontury, stínu a prostoru kolem ikon.
