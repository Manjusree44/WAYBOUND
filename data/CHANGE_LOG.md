# Hidden Trails — Corrected Dataset Change Log

Date: 2026-11-27

## Included files
- destinations.csv — preserved records and values
- food.csv — preserved records and values
- gi_products.csv — preserved records and values
- crafts.csv — preserved records and values
- cultural_experiences.csv — preserved records and values
- media_assets.csv — preserved records and values
- sources_reference.csv — corrected source-reference mapping
- unresolved_source_references.csv — source rows that could not be safely mapped

## Source-reference correction
The original sources_reference.csv used destination IDs and, in some cases, GI IDs in `record_id` for non-destination datasets. The corrected file uses the entity dataset's primary key in `record_id` and adds `destination_id` as a separate optional relationship field.

Rows were mapped using exact source URL matches and existing destination/GI relationships. Where a shared source page matched multiple records, the source was associated with each matching record. Rows without a supportable mapping were retained in unresolved_source_references.csv rather than guessed.

Original source-reference rows: 316
Corrected source-reference rows (after supported mapping and de-duplication): 319
Unresolved source-reference rows: 0

## Validation
- Original entity/media record counts retained: 45 destinations, 15 food, 40 GI products, 20 crafts, 13 cultural experiences, 12 media assets.
- Primary IDs and entity field values were not intentionally changed.
- The corrected source-reference `record_id` values are checked against the primary IDs of their declared dataset, except any row preserved only if it already had a valid primary ID.
- `destination_id` is a separate optional association and is not used as a substitute for the entity primary key.

## Limitations
This is a structural source-reference correction, not a factual audit of every source URL or claim. No external factual claims, prices, availability, licensing, or GI legal status have been newly verified.
