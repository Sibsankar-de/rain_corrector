# External data cache

Cached responses from third-party providers, so a re-run does not depend on an
external service being available.

Empty by default. `ENABLE_EXTERNAL_INGESTION` is `false` in the shipped
configuration, and nothing in the pipeline requires this directory to be
populated.

## Provider selection

`DATA_PROVIDER` selects the implementation behind the interface in
`backend/app/data/providers/`:

| Value | Behaviour |
| --- | --- |
| `local_csv` | Default. Reads `data/processed/`. No network access |
| `open_meteo` | Fetches a forecast API. Requires `ENABLE_EXTERNAL_INGESTION=true` and network access |

## If you enable external ingestion

1. Read the provider's terms and rate limits first.
2. Record the source and the retrieval date in a `SOURCE.md` here.
3. Cache the raw response before parsing it, so a schema change upstream is
   visible as a diff rather than as different numbers.
4. Keep the API key in the environment, never in a file committed to the
   repository.

## Terms and rate limits

Respect them. A provider that disallows bulk retrieval should be sampled or
licensed, not worked around.
