# Authoritative Indian Environmental & Disaster Forecasting Datasets

This document provides complete documentation of the real-world datasets acquired from official Indian government sources (Central Water Commission / National Water Data Portal, Central Pollution Control Board / Open Government Data) and integrated into the `rain-corrector` project.

---

## 1. Executive Summary & Storage Budget

| Metric | Target / Limit | Actual Realised | Status |
| :--- | :--- | :--- | :--- |
| **Total Raw Downloaded Size** | Preferred $\le$ 1.0 GB / Hard Max $\le$ 5.0 GB | **217.63 MB** (0.213 GB) | **PASS (Preferred)** |
| **Total Processed Dataset Size** | Compact / Low Memory Footprint | **1.77 MB** | **PASS** |
| **Monitoring Stations** | Representative regional basin network | **351 stations** | **PASS** |
| **Districts Covered** | Compact regional focus | **25 districts** (Maharashtra & Godavari Basin) | **PASS** |
| **Historical Period** | 3–5 years recommended | **5 years** (2021-01-01 to 2025-12-31) | **PASS** |
| **Data Fabrication** | Zero fake/synthetic records in training | **0 records fabricated** | **PASS** |

---

## 2. Acquired Authoritative Datasets

### Dataset 1: CWC Maharashtra Telemetry Hourly Rainfall
- **Publisher**: Central Water Commission (CWC), Ministry of Jal Shakti, Government of India
- **Official Portal**: National Water Data Portal (NWDP / NWIC)
- **Official URL**: `https://www.nwdp.nwic.gov.in/en/dataset/rainfall-cwc-telemetry-hourly`
- **Download/API URL Actually Used**: `https://nwdp.nwic.gov.in/dataset/4b998cf7-1ab6-48c6-bb50-a9226cb17dd4/resource/7432cb1f-4efc-4e89-8d26-78cc738a9da9/download/rainfall_tel_hr_cwc_mh_2021_2025.csv`
- **Geographical Coverage**: Maharashtra State, India (22 districts: Kolhapur, Gadchiroli, Nanded, Jalgaon, Chandrapur, Amravati, Parbhani, Nashik, Dhule, Bhandara, Wardha, Aurangabad, Hingoli, Ahmadnagar, Satara, Yavatmal, Nandurbar, Solapur, Thane, Akola, Buldana, Sangli)
- **Spatial Coordinates**: Lat [16.68, 21.52]°N, Lon [73.27, 80.09]°E
- **Time Range**: 2021-01-01 05:30 to 2025-12-29 14:30 IST
- **Spatial Resolution**: Point telemetry stations (58 active tipping-bucket rain gauges)
- **Temporal Resolution**: Hourly telemetry transmissions
- **Variables**: `Telemetry Hourly Rainfall (mm)`, `Station`, `Agency`, `District`, `River`, `Basin`, `Latitude`, `Longitude`, `Data Acquisition Time`
- **File Format**: CSV (Raw: 35.02 MB, 266,707 records; Processed daily: 0.59 MB, 11,731 rows)
- **License / Access**: Open Government Data (OGD) India / Ministry of Jal Shakti NWDP Public Access
- **Purpose in Model**: Ground truth daily precipitation target and antecedent precipitation indices (1d, 3d, 7d, 14d, 30d rolling rainfall sums, dry streak duration).
- **Preprocessing Performed**:
  - Filtered sensor offline error codes (`value < 0`).
  - Flagged and filtered stuck sensor ADC saturation (`Lasur` station stuck at 511.5 mm).
  - Filtered unphysical single-hour rain rates (> 150 mm/hr).
  - Imputed dry gauge hours (no tipping trigger = 0.0 mm).
  - Aggregated hourly telemetry to station daily sums, then computed district-level daily mean precipitation.

---

### Dataset 2: CWC Godavari River Basin Telemetry Hourly River Water Level
- **Publisher**: Central Water Commission (CWC), Ministry of Jal Shakti, Government of India
- **Official Portal**: National Water Data Portal (NWDP / NWIC)
- **Official URL**: `https://nwdp.nwic.gov.in/dataset/river-water-level-telemetry-hourly-central-water-commission-cwc`
- **Download/API URL Actually Used**: `https://nwdp.nwic.gov.in/dataset/02b2605f-fc8c-4a3e-b83b-e2e71887e089/resource/977ecb3c-e6fc-469b-9ffb-ce26715f2a1b/download/rwl_tel_hr_cwc_006_2021_2025.csv`
- **Geographical Coverage**: Godavari River Basin (Maharashtra, Telangana, Chhattisgarh, Andhra Pradesh, Odisha)
- **Spatial Coordinates**: Lat [16.94, 22.32]°N, Lon [73.80, 82.51]°E (66 river gauging telemetry stations)
- **Time Range**: 2021-01-01 00:00 to 2025-12-29 23:30 IST
- **Spatial Resolution**: Telemetry river stage stations
- **Temporal Resolution**: Hourly automated telemetry
- **Variables**: `River Water Level Telemetry Hourly (meter)`, `MeanSeaLevel`, `RL_of_zeroGauge`, `Is_DischargeDataAvailable`, `River`, `Basin`, `Latitude`, `Longitude`
- **File Format**: CSV (Raw: 177.11 MB, 1,055,737 records; Processed: included in `flood_features.parquet`)
- **License / Access**: OGD India / CWC Telemetry
- **Purpose in Model**: Hydrological state representation (mean daily river stage, maximum daily river stage, antecedent 24-hour river stage rate of change $\Delta h_{24\text{h}}$).
- **Preprocessing Performed**:
  - Filtered negative uncalibrated sensor values (< 0 m).
  - Interpolated short telemetry dropouts ($\le 6$ hours) using forward linear interpolation per station series.
  - Retained missing indicators for dropouts $> 6$ hours.
  - Aggregated to district-level daily mean stage and computed 1-day shifted antecedent rate of change ($\Delta h_{24\text{h}} = h_{t-1} - h_{t-2}$) to guarantee strict zero-leakage.

---

### Dataset 3: CWC River Water Discharge Telemetry
- **Publisher**: Central Water Commission (CWC), Ministry of Jal Shakti, Government of India
- **Official Portal**: National Water Data Portal (NWDP / NWIC)
- **Official URL**: `https://nwdp.nwic.gov.in/dataset/river-discharge-telemetry-hourly-central-water-commission-cwc`
- **Download/API URL Actually Used**: `https://nwdp.nwic.gov.in/dataset/4c5fc698-c115-4ba8-9a99-b1d5329c071d/resource/4ea81f5c-8df3-4c91-a189-bc8c91979b94/download/river_discharge_tele_hr_cwc_od_1970_2025.csv`
- **Geographical Coverage**: Eastern Peninsular river telemetry reference station (Champua station, Baitarani Basin)
- **Spatial Coordinates**: Lat 22.07°N, Lon 85.68°E
- **Time Range**: 2022-09-01 to 2025-12-31
- **Spatial Resolution**: Point hydrometric telemetry station
- **Temporal Resolution**: Hourly discharge observations
- **Variables**: `Telemetry Hourly River Water Discharge (m3/sec)`
- **File Format**: CSV (Raw: 4.41 MB, 43,538 records)
- **License / Access**: OGD India / CWC
- **Purpose in Model**: Regional hydrological response proxy (river flow dynamics under intense monsoon precipitation).
- **Preprocessing Performed**:
  - Filtered negative transmission error codes (e.g., $-11797$ m$^3$/s).
  - Forward-interpolated gaps $\le 6$ hours.
  - Computed daily mean and maximum discharge, shifted by 1 day as antecedent feature.

---

### Dataset 4: CWC Maharashtra Telemetry Air Temperature
- **Publisher**: Central Water Commission (CWC), Ministry of Jal Shakti, Government of India
- **Official Portal**: National Water Data Portal (NWDP / NWIC)
- **Official URL**: `https://nwdp.nwic.gov.in/dataset/rainfall-cwc-telemetry-hourly`
- **Download/API URL Actually Used**: `https://nwdp.nwic.gov.in/dataset/4b998cf7-1ab6-48c6-bb50-a9226cb17dd4/resource/719d3f44-6724-4f10-b99b-34a9190db998/download/temprature_tel_hr_cwc_mh_2021_2025.csv`
- **Geographical Coverage**: Tapi River Basin (Bhusawal, Jalgaon, Maharashtra)
- **Time Range**: 2021-01-01 to 2022-08-23
- **Spatial Resolution**: Point meteorological telemetry
- **Temporal Resolution**: Hourly
- **Variables**: `Air Temperature Telemetry Hourly (ºC)`
- **File Format**: CSV (Raw: 0.61 MB, 5,123 records)
- **License / Access**: OGD India / CWC
- **Purpose in Model**: Evapotranspiration proxy and thermal seasonal driver.
- **Preprocessing Performed**:
  - Filtered negative sensor uncalibrated codes ($< 0^\circ\text{C}$).
  - Aggregated to daily mean and max temperature.

---

### Dataset 5: CPCB Surface Water Chemical Parameters
- **Publisher**: Central Pollution Control Board (CPCB), Ministry of Environment, Forest and Climate Change, Government of India
- **Official Portal**: National Water Data Portal (NWDP / NWIC) & data.gov.in
- **Official URL**: `https://nwdp.nwic.gov.in/dataset/surface-water-quality-chemical-parameter-manual-cpcb`
- **Download/API URL Actually Used**: `https://nwdp.nwic.gov.in/dataset/a84f3c7e-e1eb-4752-95f2-95726ce73fc4/resource/66bb6b38-df64-4e4b-bbd8-4fbe1b8c005f/download/swq_chemical_parameter_manual_cpcb_mh_2021_2025.csv`
- **Geographical Coverage**: Maharashtra State (31 districts, 225 monitoring stations)
- **Time Range**: 2021-01-01 to 2021-12-28
- **Spatial Resolution**: Monitoring stations across rivers and reservoirs
- **Variables**: Dissolved Oxygen (`mg/L`), Potential of Hydrogen (`pH`), Total Dissolved Solids (`mg/L`), Nitrate-N (`mgN/L`), Total Hardness (`mgCaCO3/L`), Total Alkalinity (`mg/L`)
- **File Format**: CSV (Raw: 0.47 MB, 1,942 records; Processed parquet: 42.23 KB, 4,022 records)
- **License / Access**: Open Government Data (OGD) India
- **Purpose in Model**: Environmental and water quality baseline monitoring; surface water runoff contamination tracking during flood flush events.
- **Preprocessing Performed**:
  - Filtered non-positive physical values.
  - Normalised to the standard schema: `[timestamp, station_id, station_name, district_id, latitude, longitude, parameter, value, unit, qc_flag, source]`.
  - Exported to `data/processed/air_quality_features.parquet`.

---

## 3. Study Region & Geographical Rationale

The selected region is **Maharashtra State and the Godavari River Basin**, India.
- **Why this region?**
  1. Highly prone to severe monsoon flooding (Godavari, Krishna, and Tapi river basins).
  2. Dense real telemetry infrastructure deployed by CWC with automated 1-hour updates.
  3. Co-located hydrological (river stage, discharge), meteorological (rainfall, temperature), and environmental (CPCB water quality) stations.
  4. Fully compact: 25 districts, total raw dataset size under 220 MB, well within the $\le 1$ GB preferred target.

---

## 4. Missing Data & Quality Control Protocol

| Source Dataset | Missing / Offline Rate | Nature of Gaps | Resolution Strategy |
| :--- | :--- | :--- | :--- |
| **CWC Rainfall** | 91.53% (non-tipping hours) | Non-monsoon dry intervals & sensor dropouts | Zero-rainfall assignment for inactive gauge periods; stuck sensor ($511.5$ mm) at Lasur masked to NaN. |
| **CWC Water Level** | 1.57% | Temporary packet loss / sensor resets | Short gaps ($\le 6$ h) linearly interpolated forward; longer gaps flagged as NaN; district median used for unmonitored districts. |
| **CWC Discharge** | 63.86% (gauge uninitialized) | Negative telemetry error flags ($-11797$) | Filtered $< 0$ to NaN; short gaps ($\le 6$ h) interpolated; lag shifted by 1 day. |
| **CWC Temperature** | 20.05% | Sensor negative glitch flags ($-0$, $-41.8$) | Filtered $< 0$ to NaN; daily mean aggregated. |
| **CPCB Quality** | 4.79% | Irregular grab sample schedules | Standard long-format normalization; explicit `qc_flag="PASS"`. |

### Zero-Leakage Guarantee
All hydrological and precipitation lag features are computed strictly antecedent to the forecast issue date:
- Rolling rainfall windows: `shift(1).rolling(w).sum()`
- Antecedent 24h water level change: $h_{t-1} - h_{t-2}$
- Cyclical day-of-year terms: evaluated on target date $t+1$ (which is deterministically known at issuance)
- Enforced at test time by `assert_no_leakage(frame)` in `ml/src/rainml/features/engineering.py`.

---

## 5. Machine-Readable Metadata

The complete machine-readable manifest is stored at:
[`data/metadata/datasets.json`](file:///home/sibsankar_de/projects/rain-corrector/data/metadata/datasets.json)

---

## 6. How to Reproduce

1. **Download Raw Data**:
   ```bash
   python scripts/download_data.py
   ```
2. **Validate Dataset Budget & Integrity**:
   ```bash
   python scripts/validate_data.py --fail-on-missing
   ```
3. **Preprocess & Engineer Features**:
   ```bash
   python scripts/preprocess_data.py
   ```
4. **Train Model on Real Data**:
   ```bash
   python scripts/train.py --promote
   ```
5. **Evaluate on Holdout Partition**:
   ```bash
   python scripts/evaluate.py
   ```
6. **Issue Forecasts**:
   ```bash
   python scripts/predict.py --districts MH-NAS,MH-JAL,MH-KOL
   ```
