"""\"API as a Product\" endpoints, consumed by other teams' tooling.

Every one is an unpaginated flat list documented via drf-spectacular. Field
names and response shapes are a published contract -- changing them breaks
consumers who will not find out until their next scrape.
"""
