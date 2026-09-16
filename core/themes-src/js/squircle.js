/**
 * Převede nezáporný rozměr s jednotkou px, %, vw nebo vh na pixely.
 *
 * parentSize: rozměr rodiče v právě počítané ose (procentní základ).
 * viewportWidth / viewportHeight: šířka a výška zvolené plochy monitoru.
 * Všechny vstupní rozměry musí používat stejný souřadnicový systém.
 */
export function toPixels(value, {parentSize, viewportWidth, viewportHeight} = {}) {
    if (typeof value !== 'string')
        throw new TypeError('Rozměr musí být text s jednotkou, například "80vw".');

    // Oddělíme číslo a jednotku: například "12.5vh" → "12.5" a "vh".
    const match = value.trim().match(/^(\d+(?:\.\d+)?|\.\d+)(px|%|vw|vh)$/);
    if (!match)
        throw new Error(`Neplatný rozměr "${value}". Použij px, %, vw nebo vh.`);

    const amount = Number(match[1]);
    const unit = match[2];
    if (!Number.isFinite(amount))
        throw new RangeError('Číselná hodnota rozměru je příliš velká.');

    // Pixely už jsou výslednou jednotkou; nepotřebují žádný základ.
    if (unit === 'px')
        return amount;

    let base;
    switch (unit) {
    case '%':
        base = parentSize;
        break;
    case 'vw':
        base = viewportWidth;
        break;
    case 'vh':
        base = viewportHeight;
        break;
    }

    if (!Number.isFinite(base) || base < 0)
        throw new RangeError(`Pro jednotku "${unit}" chybí platný nezáporný základ.`);

    const pixels = amount / 100 * base;
    if (!Number.isFinite(pixels))
        throw new RangeError('Výsledný rozměr je příliš velký.');

    return pixels;
}

// Rozměry SVG pozadí, nikoli dialogu nebo mřížky ikon.
export const folderBackground = Object.freeze({
    width: '100%',
    height: '100%',
    inset: '0px',
    dockGap: '24px',
});

/** Stage coordinates in; CSS lengths out. Only a bottom horizontal dock applies. */
export function calculateDockClearance(monitor, area, dock, scale, gap = folderBackground.dockGap) {
    if (!dock || dock.width <= 0 || dock.height <= 0 || dock.width < dock.height ||
        dock.x >= monitor.x + monitor.width || dock.x + dock.width <= monitor.x ||
        dock.y < monitor.y + monitor.height / 2 || dock.y >= monitor.y + monitor.height)
        return null;
    const distance = toPixels(gap, {
        parentSize: area.height / scale,
        viewportWidth: area.width / scale,
        viewportHeight: area.height / scale,
    }) * scale;
    const top = Math.max(monitor.y, area.y);
    const bottom = Math.max(top + 1, Math.min(area.y + area.height, dock.y - distance));
    return {
        top: (top - monitor.y) / scale,
        bottom: (monitor.y + monitor.height - bottom) / scale,
        maxHeight: (bottom - top) / scale,
    };
}

/** St rejects a declaration list beginning with a semicolon. */
export function folderBackgroundStyle(originalStyle, {width, height, x, y}) {
    const original = (originalStyle ?? '').trim().replace(/;+\s*$/, '');
    const prefix = original ? `${original}; ` : '';
    return `${prefix}background-size: ${width}px ${height}px !important; background-position: ${x}px ${y}px !important; background-repeat: no-repeat !important;`;
}

/** Všechny rozměry jsou v CSS px (adaptér předem odečte theme scale). */
export function calculateFolderBackground(actorSize, viewport, options = folderBackground) {
    const {width, height} = actorSize;
    if (![width, height, viewport.width, viewport.height].every(n => Number.isFinite(n) && n > 0))
        throw new RangeError('Dialog a pracovní plocha musí mít kladné rozměry.');

    const dimensions = {viewportWidth: viewport.width, viewportHeight: viewport.height};
    const along = (value, parentSize) => toPixels(value, {...dimensions, parentSize});
    const insetX = Math.min(along(options.inset, width), Math.max(0, (width - 1) / 2));
    const insetY = Math.min(along(options.inset, height), Math.max(0, (height - 1) / 2));
    const imageWidth = Math.min(along(options.width, width), width - 2 * insetX);
    const imageHeight = Math.min(along(options.height, height), height - 2 * insetY);
    if (imageWidth <= 0 || imageHeight <= 0)
        throw new RangeError('SVG pozadí musí mít kladné rozměry.');
    return {
        width: imageWidth,
        height: imageHeight,
        x: (width - imageWidth) / 2,
        y: (height - imageHeight) / 2,
    };
}
