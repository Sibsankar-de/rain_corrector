# Model artifacts

One directory per version, written by `scripts/run_training.py` and the
`rainml` training pipeline.

```text
ml/artifacts/
├── v001/
│   ├── model.joblib          fitted pipeline (preprocessor + regressor)
│   ├── lower_model.joblib    10th percentile pipeline
│   ├── upper_model.joblib    90th percentile pipeline
│   ├── preprocessor.joblib   fitted ColumnTransformer, exported separately
│   ├── feature_columns.json  exact training-time feature order
│   ├── metadata.json         model card
│   ├── metrics.json          split metrics for baselines and candidates
│   └── checksum.txt          sha256 of model.joblib
├── v002/
└── active -> v002            optional symlink for single-artifact deployments
```

## Rules

* **Versions are immutable.** A retraining run always writes a new directory.
  Overwriting an existing version is refused unless `overwrite=True` is passed
  explicitly, and doing so is a mistake: the database still references the old
  artifact, and the metrics in the model card would no longer match it.
* **The API serves exactly one version at a time**, tracked by
  `model_versions.status = 'active'` in PostgreSQL. Pointing the backend at a
  different directory is done by promoting a version, not by deleting files.
* `MODEL_VERSION` in the environment pins a specific version and overrides the
  database flag, which is what a reproducible evaluation deployment does.
* Artifacts are ignored by git (`.gitignore`). Rebuild them with
  `python scripts/run_training.py`.
