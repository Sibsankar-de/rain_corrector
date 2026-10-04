# Raw data

Source data exactly as obtained, never modified. Kept so a training run is
reproducible from the original input.

The bundled demo dataset is **not** here: it is generated into `../processed/`
by `scripts/generate_demo_dataset.py`. See [`../README.md`](../README.md) for its
provenance and for the schema a real source must match.

## Layout

```text
raw/
  <source-name>/
    <download-date>/
      <original files, unmodified>
```

## Adding a source

1. Record the URL, the retrieval date and the licence in a `SOURCE.md` next to
   the files.
2. Keep the original format. Convert later, in the loader, not on disk.
3. Do not rename columns here. The loaders expect the schema in
   [`../README.md`](../README.md).

## Licensing

Only store data you are permitted to use. Free and open sources for this
domain include the India Meteorological Department (subject to its terms) and
ERA5 via the Copernicus Climate Data Store. Record the terms alongside the data;
"it was downloadable" is not a licence.
