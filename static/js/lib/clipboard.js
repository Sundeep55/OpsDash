/**
 * Copy text to the clipboard.
 *
 * navigator.clipboard is unavailable on insecure origins, which includes plain
 * HTTP hostnames -- so it cannot be relied on for anyone reaching the portal
 * over http:// internally. Falls back to a hidden textarea and execCommand,
 * which is deprecated but still the only thing that works there.
 */
export async function copyText(text) {
    const value = String(text ?? '');
    if (!value) return false;

    if (navigator.clipboard && window.isSecureContext) {
        try {
            await navigator.clipboard.writeText(value);
            return true;
        } catch {
            // Permission denied or the document is not focused; try the fallback.
        }
    }

    const textarea = document.createElement('textarea');
    textarea.value = value;
    // Keep it out of view and off the tab order, and stop iOS zooming to it.
    textarea.setAttribute('readonly', '');
    textarea.setAttribute('aria-hidden', 'true');
    textarea.tabIndex = -1;
    textarea.style.cssText = 'position:fixed;top:0;left:-9999px;opacity:0;';
    document.body.appendChild(textarea);

    try {
        textarea.select();
        return document.execCommand('copy');
    } catch {
        return false;
    } finally {
        textarea.remove();
    }
}
