/**
 * HTTP access to the internal API.
 *
 * Every read goes through getJSON so URL building, error handling and the
 * session-expiry case live in one place rather than being repeated per fetch.
 */

/** Read a cookie by name. Needed for Django's CSRF token on writes. */
export function getCookie(name) {
    const prefix = name + '=';
    for (const cookie of document.cookie.split(';')) {
        const trimmed = cookie.trim();
        if (trimmed.startsWith(prefix)) {
            return decodeURIComponent(trimmed.slice(prefix.length));
        }
    }
    return null;
}

/**
 * Build a query string, dropping empty values.
 *
 * Callers used to concatenate `&key=` fragments by hand, which meant every new
 * filter was another chance to forget encodeURIComponent.
 */
export function buildQuery(params) {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
        if (value === undefined || value === null || value === '' || value === false) continue;
        search.append(key, value);
    }
    const query = search.toString();
    return query ? `?${query}` : '';
}

/** Raised when the session has gone; the app reloads to reach the login page. */
export class SessionExpired extends Error {}

async function request(url, options = {}) {
    const response = await fetch(url, options);

    // DRF answers an unauthenticated request with 403 (SessionAuthentication
    // supplies no WWW-Authenticate header, so it never becomes a 401 prompt).
    if (response.status === 401 || response.status === 403) {
        throw new SessionExpired(`Session expired for ${url}`);
    }
    if (!response.ok) {
        // Carry the server's own explanation on the error rather than throwing
        // it away. DRF puts it in `detail`, and for the pipeline endpoints that
        // is the only place GitLab's reason appears -- "there can not be more
        // than 20 inputs", "insufficient permissions". A bare "HTTP 502" tells
        // the operator nothing they can act on.
        //
        // The message keeps its original shape, because callers match on it:
        // useSync tests for '409'.
        let detail = '';
        try {
            const body = await response.json();
            detail = body && (body.detail || body.message || body.error) || '';
        } catch { /* not JSON; the status is all there is */ }

        const error = new Error(`HTTP ${response.status} for ${url}`);
        error.status = response.status;
        error.detail = typeof detail === 'string' ? detail : JSON.stringify(detail);
        throw error;
    }
    return response.json();
}

export function getJSON(path, params) {
    return request(path + (params ? buildQuery(params) : ''));
}

export function postJSON(path, body, headers = {}) {
    return request(path, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken'),
            // Callers may add their own -- the pipeline trigger passes the
            // operator's GitLab token this way, so it never enters the body.
            ...headers,
        },
        body: body ? JSON.stringify(body) : undefined,
    });
}

/** Read the JSON config the template embeds, so no globals are needed. */
export function readPortalConfig() {
    const element = document.getElementById('portal-config');
    if (!element) return {};
    try {
        return JSON.parse(element.textContent);
    } catch {
        return {};
    }
}
