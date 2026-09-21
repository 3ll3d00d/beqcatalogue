# BEQ filter-record contract

Version 1 defines one JSON object representing one published BEQ. A producer
writes one such object per file and a `database.json` array containing those
objects. These are **source records**, not the final public
`docs/database.json`: BEQCatalogue consumes source records, generates pages,
and adds its derived fields (`catalogue_url`, normalised audio fields and
`filterAuthor`) to the global database.

Required fields are `title`, `year`, `audioTypes`, `content_type`, `author`,
`filters`, `mv`, `digest`, `created_at` and `updated_at`. Producers must not
write `catalogue_url`; that belongs to BEQCatalogue's generated output.

`content_type` is `film` or `TV`. `audioTypes` is an array of strings.
`filters` is an array of miniDSP-style biquads. Each item has `type`, `freq`,
`gain`, `q`; shelf items also have `count`. Its `biquads["96000"]` object has
three `b` and two `a` coefficient strings. The array is unrolled: a repeated
filter appears once per biquad (and a shelf's `count` is therefore `1`).

Optional metadata fields are `altTitle`, `sortTitle`, `edition`, `season`,
`episode`, `note`, `warning`, `language`, `source`, `overview`, `rating`,
`runtime`, `collection`, `genres`, `avs`, `theMovieDB`, `images` and
`filterAuthor`. Empty optional values may be omitted.

`digest` is SHA-256 over JSON containing exactly `title`, `filters`, `mv`,
`season` and `episode`, using the catalogue's canonical serialisation.
`created_at` is retained when a record is updated; `updated_at` changes when
its digest changes. Both are Unix seconds. The individual filename is not part
of the record contract.

An aggregate `database.json` is a JSON array of the individual records, sorted
by their individual relative path. It is derived output: consumers must treat
the individual records as authoritative, and producers must rewrite it whenever
they write, update or remove a record.
