# GTK override — zatím záměrně nepoužito

GNOME 50 používá libadwaita a globální kopírování souborů do
`~/.config/gtk-4.0/gtk.css` může rozbíjet kontrast, aplikace a budoucí upgrady.
Fedora Nova 0.1 proto mění Shell, systémový dark/accent režim, ikony, fonty a
terminál, ale nepřepisuje globálně GTK4/libadwaita CSS.

V další verzi sem můžeme přidat malý, testovaný override nebo vlastní styl pro
konkrétní aplikace. Tato složka je připravená jako bezpečné místo pro pokusy.
