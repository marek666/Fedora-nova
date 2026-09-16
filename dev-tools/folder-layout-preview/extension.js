import St from 'gi://St';
import GLib from 'gi://GLib';
import {Extension, InjectionManager} from 'resource:///org/gnome/shell/extensions/extension.js';
import {AppFolderDialog} from 'resource:///org/gnome/shell/ui/appDisplay.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {calculateFolderBackground, calculateDockClearance, folderBackgroundStyle} from './squircle.js';

export default class FolderLayoutPreview extends Extension {
    enable() {
        this._dialogs = new Map();
        this._dockWatchId = 0;
        this._injections = new InjectionManager();
        const extension = this;
        this._injections.overrideMethod(AppFolderDialog.prototype, 'popup', original => {
            return function (...args) {
                extension._track(this);
                const result = original.apply(this, args);
                extension._resize(this);
                extension._watchDock();
                return result;
            };
        });
        this._workareasId = global.display.connect('workareas-changed', () => {
            for (const dialog of this._dialogs.keys())
                this._resize(dialog);
        });
        this._monitorsId = Main.layoutManager.connect('monitors-changed', () => {
            for (const dialog of this._dialogs.keys())
                this._resize(dialog);
        });
        this._themeContext = St.ThemeContext.get_for_stage(global.stage);
        this._scaleId = this._themeContext.connect('notify::scale-factor', () => {
            for (const dialog of this._dialogs.keys())
                this._resize(dialog);
        });
    }

    _watchDock() {
        if (this._dockWatchId)
            return;
        // Transformed dock geometry changes during autohide/overview animation
        // without changing its allocation. Sample only while a folder is open.
        this._dockWatchId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 100, () => {
            let open = false;
            for (const dialog of this._dialogs.keys()) {
                if (dialog._isOpen) {
                    open = true;
                    this._resize(dialog);
                }
            }
            if (open)
                return GLib.SOURCE_CONTINUE;
            this._dockWatchId = 0;
            return GLib.SOURCE_REMOVE;
        });
    }

    _dockRect() {
        // Dash to Dock 105 replaces Main.overview.dash. Both it and GNOME's
        // stock dash expose the visible background separately from icon labels.
        const actor = Main.overview.dash?._background;
        if (!actor?.get_stage() || !actor.mapped || !actor.has_allocation())
            return null;
        const [x, y] = actor.get_transformed_position();
        const [width, height] = actor.get_transformed_size();
        return {x, y, width, height};
    }

    _track(dialog) {
        if (this._dialogs.has(dialog))
            return;
        const record = {
            boxStyle: dialog._viewBox.get_style(),
            containerStyle: dialog.child.get_style(),
            allocationId: dialog._viewBox.connect('notify::allocation', () => this._resize(dialog)),
            destroyId: dialog.connect('destroy', () => this._dialogs.delete(dialog)),
        };
        this._dialogs.set(dialog, record);
    }

    _resize(dialog) {
        const monitor = Main.layoutManager.primaryMonitor;
        if (!monitor)
            return;
        const record = this._dialogs.get(dialog);
        const actor = dialog._viewBox;
        // The first popup has no allocation yet. Its allocation signal will
        // supply the actual dialog size without changing GNOME's layout.
        if (!actor.has_allocation() || actor.width <= 0 || actor.height <= 0)
            return;
        try {
            const area = Main.layoutManager.getWorkAreaForMonitor(monitor.index);
            const scale = St.ThemeContext.get_for_stage(global.stage).scale_factor;
            const clearance = calculateDockClearance(monitor, area, this._dockRect(), scale);
            const prefix = style => style?.trim() ? `${style.replace(/;+\s*$/, '')}; ` : '';
            const containerStyle = clearance
                ? `${prefix(record.containerStyle)}padding-top: ${clearance.top}px !important; padding-bottom: ${clearance.bottom}px !important;`
                : record.containerStyle;
            if (dialog.child.get_style() !== containerStyle)
                dialog.child.set_style(containerStyle);
            const result = calculateFolderBackground(
                {width: actor.width / scale, height: actor.height / scale},
                {width: area.width / scale, height: area.height / scale});
            // Keep the theme's background-image URL (app-folder-squircle.svg).
            // Background sizing stays separate from the dock clearance limit.
            let style = folderBackgroundStyle(record.boxStyle, result);
            if (clearance) {
                const maxHeight = Math.max(0, actor.get_theme_node().adjust_for_height(clearance.maxHeight * scale)) / scale;
                style += ` min-height: 0px !important; max-height: ${maxHeight}px !important;`;
            }
            // set_style may schedule another allocation; do not create a loop.
            if (actor.get_style() !== style)
                actor.set_style(style);
        } catch (error) {
            if (actor.get_style() !== record.boxStyle)
                actor.set_style(record.boxStyle);
            if (dialog.child.get_style() !== record.containerStyle)
                dialog.child.set_style(record.containerStyle);
            console.error('Fedora Nova Preview folder background:', error);
        }
    }

    disable() {
        if (this._dockWatchId) {
            GLib.source_remove(this._dockWatchId);
            this._dockWatchId = 0;
        }
        this._injections.clear();
        global.display.disconnect(this._workareasId);
        Main.layoutManager.disconnect(this._monitorsId);
        this._themeContext.disconnect(this._scaleId);
        for (const [dialog, record] of this._dialogs) {
            dialog.disconnect(record.destroyId);
            dialog._viewBox.disconnect(record.allocationId);
            dialog._viewBox.set_style(record.boxStyle);
            dialog.child.set_style(record.containerStyle);
        }
        this._dialogs.clear();
    }
}
