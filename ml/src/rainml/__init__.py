"""Rain Corrector machine learning library.

Layout:

    data/        dataset loading, cleaning, validation
    features/    feature engineering and selection
    models/      baselines, candidate models, registry
    training/    training configuration and the pipeline
    evaluation/  metrics and the evaluator
    inference/   serving-side preprocessing and predictor
"""

__version__ = "1.0.0"

MODEL_NAME = "district_daily_rainfall"
