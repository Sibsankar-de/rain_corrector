"""Dataset generation for local development and demos.

Produces a *synthetic* district rainfall series with realistic structure:
monsoon seasonality, spatial coherence between neighbouring districts,
intermittent events and measurement noise. The output is explicitly labelled so
it is never mistaken for IMD or gauge data.

Real deployments replace `data/processed/observations.csv` with an actual
dataset of the same schema; nothing else in the pipeline changes.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_SOURCE = "synthetic_demo"


@dataclass(frozen=True)
class DistrictSpec:
    code: str
    name: str
    region: str
    lat: float
    lon: float
    population: int
    coastal: bool = False


# Coordinates approximate real district locations so the map renders sensibly.
DEMO_DISTRICTS: tuple[DistrictSpec, ...] = (
    DistrictSpec("MH-MUM", "Mumbai Suburban", "Maharashtra", 19.2183, 72.9781, 2335000, coastal=True),
    DistrictSpec("MH-PUN", "Pune", "Maharashtra", 18.5204, 73.8567, 3127000),
    DistrictSpec("MH-NAG", "Nagpur", "Maharashtra", 21.1458, 79.0882, 2493000),
    DistrictSpec("KA-BLR", "Bengaluru Urban", "Karnataka", 12.9716, 77.5946, 8444000),
    DistrictSpec("KA-MYS", "Mysuru", "Karnataka", 12.2958, 76.6394, 920000),
    DistrictSpec("KL-TVM", "Thiruvananthapuram", "Kerala", 8.5241, 76.9366, 3300000, coastal=True),
    DistrictSpec("KL-EMM", "Ernakulam", "Kerala", 9.9816, 76.2999, 3280000, coastal=True),
    DistrictSpec("DL-DEL", "New Delhi", "Delhi", 28.7041, 77.1025, 3200000),
    DistrictSpec("UP-LKO", "Lucknow", "Uttar Pradesh", 26.8467, 80.9462, 3500000),
    DistrictSpec("GJ-AHM", "Ahmedabad", "Gujarat", 23.0225, 72.5714, 4400000),
    DistrictSpec("RJ-JAI", "Jaipur", "Rajasthan", 26.9124, 75.7873, 3450000),
    DistrictSpec("WB-KOL", "Kolkata", "West Bengal", 22.5726, 88.3639, 4540000, coastal=True),
    DistrictSpec("TN-MAA", "Chennai", "Tamil Nadu", 13.0827, 80.2707, 4600000, coastal=True),
    DistrictSpec("TS-HYD", "Hyderabad", "Telangana", 17.3850, 78.4867, 4100000),
    DistrictSpec("AS-GAU", "Kamrup Metropolitan", "Assam", 26.1445, 91.7362, 1100000),
    DistrictSpec("HP-SML", "Shimla", "Himachal Pradesh", 31.1048, 77.1734, 800000),
)


def _monsoon_weight(day_of_year: int, latitude: float, coastal: bool) -> float:
    """Gaussian monsoon window shifted northwards with latitude.

    Real Indian rainfall peaks in June-July in the south and July-August in the
    north; the shift with latitude is what makes a national model learnable.
    """
    peak = 195.0 + (latitude - 12.0) * 1.6
    width = 46.0 - (latitude - 12.0) * 0.6
    return float(np.exp(-0.5 * ((day_of_year - peak) / max(width, 15.0)) ** 2))


def _as_utc_day(value) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    return stamp.normalize()


def generate(
    years: int = 3,
    end_date: pd.Timestamp | None = None,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    end = _as_utc_day(end_date or pd.Timestamp.utcnow().normalize())
    start = end - pd.Timedelta(days=int(365.25 * years))
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC").normalize()

    region_state: dict[str, float] = {}
    rows: list[dict] = []

    for spec in DEMO_DISTRICTS:
        lat_factor = 1.0 + (spec.lat - 15.0) * 0.04
        wet_scale = 3.4 * lat_factor * (1.35 if spec.coastal else 1.0)
        region_state.setdefault(spec.region, float(rng.normal(0.0, 1.0)))

        for day in dates:
            doy = day.dayofyear
            seasonal = _monsoon_weight(doy, spec.lat, spec.coastal)
            # AR(1) regional weather state gives day-to-day spatial coherence.
            region_state[spec.region] = 0.72 * region_state[spec.region] + float(rng.normal(0, 0.45))
            signal = seasonal * (1.0 + 0.55 * region_state[spec.region]) + 0.18

            gamma_shape = max(signal * 0.55, 0.05)
            amount = float(rng.gamma(shape=gamma_shape, scale=wet_scale / max(gamma_shape, 0.2)))
            if rng.random() < 0.12:  # scattered convective burst
                amount += float(rng.gamma(1.6, 6.0))

            noise = float(rng.normal(0.0, 0.4))
            rainfall = max(round(amount + noise, 2), 0.0)
            rows.append(
                {
                    "district_id": spec.code,
                    "observed_at": day,
                    "rainfall_mm": rainfall,
                    "lat": spec.lat,
                    "lon": spec.lon,
                }
            )

    observations = pd.DataFrame(rows)

    districts = pd.DataFrame(
        [
            {
                "id": index + 1,
                "code": spec.code,
                "name": spec.name,
                "region": spec.region,
                "centroid_lat": spec.lat,
                "centroid_lon": spec.lon,
                "population": spec.population,
            }
            for index, spec in enumerate(DEMO_DISTRICTS)
        ]
    )
    return observations, districts


def write(output_dir: str | Path = REPO_ROOT / "data" / "processed", years: int = 3, seed: int = 42) -> dict:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    observations, districts = generate(years=years, seed=seed)
    observations_path = directory / "observations.csv"
    districts_path = directory / "districts.csv"
    observations.to_csv(observations_path, index=False)
    districts.to_csv(districts_path, index=False)

    manifest = directory / "README.md"
    return {
        "observations": str(observations_path),
        "districts": str(districts_path),
        "rows": len(observations),
        "district_count": len(districts),
        "source": SYNTHETIC_SOURCE,
        "manifest": str(manifest),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a synthetic demo rainfall dataset.")
    parser.add_argument("--output", default=str(REPO_ROOT / "data" / "processed"))
    parser.add_argument("--years", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    result = write(args.output, years=args.years, seed=args.seed)
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
