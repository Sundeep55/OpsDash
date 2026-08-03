import { getJSON } from '../lib/api.js';
import { debounce } from '../lib/util.js';

const { ref } = Vue;

/**
 * A paginated directory listing.
 *
 * The namespace, tenant and user lists were three near-identical blocks that
 * each built their own URL, unpacked the same three pagination fields and
 * carried their own debounce timer. They differ only in endpoint and query
 * parameters, which is what `buildParams` supplies.
 *
 * `isLoading` is new: the previous code left the old rows on screen during a
 * fetch, so a slow filter change looked like it had done nothing.
 */
export function usePaginatedList({ endpoint, buildParams, onError }) {
    const items = ref([]);
    const pagination = ref({ page: 1, total: 0, totalPages: 1 });
    const isLoading = ref(false);

    const fetchPage = async (page = 1) => {
        isLoading.value = true;
        try {
            const data = await getJSON(endpoint, { page, ...buildParams() });
            pagination.value = {
                page: data.current_page || page,
                total: data.count ?? 0,
                totalPages: data.total_pages || 1,
            };
            items.value = data.results || [];
        } catch (error) {
            if (onError) onError(error);
        } finally {
            isLoading.value = false;
        }
    };

    // Filter changes always return to page 1: staying on page 7 of a result set
    // that now has 2 pages shows an empty table.
    const refresh = debounce(() => fetchPage(1));

    return { items, pagination, isLoading, fetchPage, refresh };
}

/**
 * A search-driven listing with no pagination (siglums, request tickets).
 * `initial` keeps the shape the templates expect before the first response.
 */
export function useSearchList({ endpoint, buildParams, initial, onError }) {
    const data = ref(initial);
    const isLoading = ref(false);

    const fetchData = async () => {
        isLoading.value = true;
        try {
            data.value = await getJSON(endpoint, buildParams());
        } catch (error) {
            if (onError) onError(error);
        } finally {
            isLoading.value = false;
        }
    };

    return { data, isLoading, fetchData, refresh: debounce(fetchData) };
}
