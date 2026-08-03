"""API layer, split by consumer.

    internal/   endpoints the Vue SPA calls; may change freely with the frontend
    product/    "API as a Product" endpoints other teams scrape; a stable contract

The split is by audience before entity on purpose: the two halves have
different compatibility obligations, and that is the fact most likely to be
forgotten when changing a response shape.

Shared between them:
    pagination.py   page-number pagination for the internal list views
    filters.py      query filters, plus the CPU/memory quantity parsers
"""
