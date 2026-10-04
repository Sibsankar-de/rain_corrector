# Diagrams

Source diagrams live in [ARCHITECTURE.md](../../ARCHITECTURE.md), rendered with
Mermaid. This file collects the ones worth reading on their own, plus the
data-flow views that are easier to reason about as a picture than as prose.

## 1. System context

```mermaid
graph TB
    Operator["Operator"] --> Web["Rain Corrector web app"]
    Gauge["Rain gauges"] --> API["Rain Corrector API"]
    Ext["Open data provider<br/>(optional)"] --> API
    Web --> API
    API --> DB[("PostgreSQL")]
    API --> Art[("Model artifacts")]
    Sched["Scheduler"] --> Jobs["Batch jobs"]
    Jobs --> Art
    Jobs --> DB
    Art -.->|"joblib, once per version"| API
```

The operator, the gauges, the scheduler and the database are outside the
boundary. The API is the only component that serves user traffic.

## 2. Request and inference path

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant M as RequestContext
    participant R as /forecasts/generate
    participant G as ForecastGenerator
    participant REG as ModelRegistry
    participant AGG as district_aggregates
    participant P as rainml preprocessing
    participant S as sklearn pipeline
    participant A as AlertService
    participant V as verification_results

    B->>M: POST /api/v1/forecasts/generate
    M->>M: bind request_id, start timer
    M->>R: validated body
    R->>G: generate(horizon, districts)
    G->>REG: get_active()  (cached)
    REG-->>G: ModelArtifact
    G->>AGG: history strictly before issue_time
    AGG-->>G: daily rainfall per district
    G->>P: build_feature_frame(histories, issue_date)
    P-->>G: DataFrame in FEATURE_COLUMNS order
    G->>S: predict_interval(features)
    S-->>G: point, lower, upper (ordered)
    G->>G: persist run, forecasts, values
    G-->>R: run_uid, count
    R->>A: evaluate_forecasts
    A-->>R: alerts created
    R-->>M: 201 + payload
    M-->>B: X-Request-ID, X-Process-Time
```

## 3. Verification path

```mermaid
sequenceDiagram
    autonumber
    participant J as Job or POST /verification/run
    participant S as VerificationService
    participant F as forecasts
    participant AG as district_aggregates
    participant V as verification_results
    participant B as verification_batches

    J->>S: run_verification(model_version, lookback_days)
    S->>F: candidates where target_time <= now - grace
    S->>B: open a batch record
    loop each candidate
        alt already verified and not forced
            S->>S: skip
        else
            S->>AG: aggregate whose window contains target_time
            alt no observation
                S->>V: missing_observation, stays pending
            else window misplaced
                S->>S: _assert_no_leakage raises, run fails
            else matched
                S->>V: error, MAE, bias, NSE, Brier,<br/>hit / false_alarm / missed / correct_negative
                S->>F: status = verified
            end
        end
    end
    S->>B: counts and a metrics snapshot
    S-->>J: batch_uid, metrics
```

Two invariants in that loop are load-bearing: an unmatched observation leaves the
forecast pending rather than scoring it as zero, and a misplaced window raises
rather than scoring the wrong period.

## 4. Retraining and promotion

```mermaid
stateDiagram-v2
    [*] --> candidate: run_training registers
    candidate --> validated: passes policy review
    candidate --> rejected: fails review
    candidate --> active: auto_promote_if_better, beats incumbent
    validated --> active: promote
    active --> archived: superseded by a newer active
    archived --> active: force (rollback)
    rejected --> [*]

    note right of active
        Exactly one version is active.
        Activating one archives the incumbent
        in the same transaction.
    end note

    note right of candidate
        Training never promotes.
        Promotion is a separate, deliberate act.
    end note
```

## 5. Data flow

```mermaid
flowchart LR
    subgraph sources["Sources"]
        CSV["data/processed/observations.csv<br/>(synthetic demo)"]
        GAUGE["Station readings"]
        EXT["External provider"]
    end

    subgraph ingest["Ingestion"]
        API["POST /observations/ingest"]
        AGG["compute_daily_aggregates"]
    end

    subgraph store["PostgreSQL"]
        OBS[("observations<br/>station x window")]
        DAG[("district_aggregates<br/>daily per district")]
        FC[("forecasts")]
        VR[("verification_results")]
    end

    subgraph train["Training (batch)"]
        LOAD["load + clean + engineer"]
        SPLIT["chronological split"]
        FIT["fit baselines + candidates"]
        ART["ml/artifacts/&lt;version&gt;/"]
    end

    subgraph serve["Serving"]
        HIST["30-day history"]
        FEAT["build features"]
        PRED["predict_interval"]
        ALERT["severity -> alerts"]
    end

    GAUGE --> API
    EXT -.-> API
    API --> OBS --> AGG --> DAG
    CSV --> LOAD
    DAG --> LOAD
    LOAD --> SPLIT --> FIT --> ART
    DAG --> HIST --> FEAT
    ART --> PRED
    FEAT --> PRED
    PRED --> FC
    PRED --> ALERT
    FC --> VR
    DAG --> VR
```

`district_aggregates` is the single junction: it feeds both the training dataset
and the verification ground truth, so the two cannot disagree about what a
district's rainfall was.

## 6. Layering

```mermaid
graph TB
    subgraph fe["Frontend"]
        R["app/ routes"] --> H["features/*/hooks"] --> S["services/ (fetch)"] --> C["HTTP"]
    end
    subgraph be["Backend"]
        RT["api/routes"] --> SV["services"] --> RE["repositories"] --> PG[("PostgreSQL")]
        RT --> SC["schemas (Pydantic)"]
        SV --> MI["ml/ registry + predictor"] --> MF[("artifacts")]
    end
    subgraph mlpkg["ML package"]
        D["data"] --> F["features"] --> MO["models"] --> T["training"]
        T --> EV["evaluation"]
        EV --> INF["inference"]
    end
    subgraph nb["Notebooks"]
        N1["01..06"]
    end
    C --> RT
    N1 --> mlpkg
    INF -.->|"serving features"| MI
    AR["scripts/run_training.py"] --> T
    AR --> PG
```

Arrows point in the allowed direction only. There is no path from the frontend
to the database or to a model, and no path from `rainml` back into the backend.

## 7. Component ownership

```mermaid
graph LR
    subgraph config["Configuration"]
        ENV[".env"]
    end
    subgraph backend
        CFG["app/core/config.py"]
        LOG["app/core/logging_config.py"]
        SEC["app/core/security.py"]
        ERR["app/core/exceptions.py"]
        DB["app/core/database.py"]
    end
    subgraph frontend
        FCFG["lib/config.ts"]
        SEV["lib/severity.ts"]
        FMT["lib/format.ts"]
        QK["lib/query-keys.ts"]
        QC["lib/query-client.ts"]
    end
    ENV --> CFG
    ENV --> FCFG
    CFG --> DB
    CFG --> LOG
    CFG --> SEC
    ERR --> RT2["api error handlers"]
    FCFG --> MAP["map tile provider"]
    SEV --> MAP
    SEV --> TBL["tables and charts"]
    FMT --> TBL
    QK --> QC
```

One configuration source per runtime. The severity tokens are defined once on the
server (`app/services/severity.py`, served at `/forecasts/legend`) and mirrored
for display in the client, so a band change propagates rather than drifting.
