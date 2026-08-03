/** Small helpers with no dependencies. */

/**
 * Call `fn` only once the caller has stopped calling for `delay` ms.
 *
 * Every keystroke in a search box used to schedule its own request; the last
 * one to arrive won, which is not necessarily the last one sent.
 */
export function debounce(fn, delay = 300) {
    let timer = null;
    const debounced = (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), delay);
    };
    debounced.cancel = () => clearTimeout(timer);
    return debounced;
}

/** "All" is the UI's own sentinel for "do not filter", never a cluster name. */
export const ALL = 'All';

export function clusterParam(value) {
    return value && value !== ALL ? value : undefined;
}

/** Map the tri-state status pill onto the API's boolean. */
export function decommissionedParam(status) {
    if (status === 'active') return 'false';
    if (status === 'decomm') return 'true';
    return undefined;
}
