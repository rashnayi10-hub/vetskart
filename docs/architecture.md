# Architecture Notes

## Data input

Two synthetic CSV feeds model inbound service requests and participating provider records. In production, these could come from authenticated APIs or internal business systems.

## Transformations

Request validation checks required fields, coordinate ranges, timestamp timezone presence, and duplicate IDs. Provider filtering checks active availability, supported service types, and geographic service radius.

## Allocation

Requests are ordered by request time and identifier. For each request, the closest eligible, unreserved veterinarian is assigned. This is an offline batch algorithm and does not guarantee optimal global matching.

## Storage and metrics

The pipeline writes two relational tables to SQLite and exports assignment and rejection metrics. Upserts avoid duplicate records across repeated runs. The service remains illustrative, with no production-grade concurrency or privacy guarantees.
