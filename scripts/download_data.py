#!/usr/bin/env python3
"""Reproducible Downloader for Authoritative Indian Government Datasets.

Features:
- Reads configuration from data/config/data_sources.yaml
- Checks if files already exist to avoid duplicate downloads
- Verifies storage budgets: stops if cumulative raw downloads exceed limit (hard 5 GB, preferred <= 1 GB)
- Progress tracking, retry logic, timeout and SSL error handling
- Records metadata (URL, timestamp, size, sha256 checksum)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "data" / "config" / "data_sources.yaml"
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw"
DEFAULT_METADATA_DIR = REPO_ROOT / "data" / "metadata"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download real-world environmental & disaster datasets from Indian government portals."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to data sources YAML configuration",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_RAW_DIR,
        help="Directory to save raw downloads",
    )
    parser.add_argument(
        "--metadata-dir",
        type=Path,
        default=DEFAULT_METADATA_DIR,
        help="Directory to save download metadata manifests",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Specific source key to download (e.g. cwc_rainfall)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if files already exist",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1024 * 1024,  # 1 MB
        help="Download chunk size in bytes",
    )
    return parser.parse_args(argv)


def _compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _get_remote_size(url: str, ctx: ssl.SSLContext) -> int | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="HEAD")
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            cl = resp.headers.get("Content-Length")
            return int(cl) if cl else None
    except Exception:
        return None


def download_file(
    url: str,
    target_path: Path,
    expected_name: str,
    max_bytes_allowed: int,
    current_total_bytes: int,
    chunk_size: int = 1024 * 1024,
    retries: int = 3,
) -> tuple[int, str]:
    """Download a file with streaming, progress reporting, and budget check."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    remote_size = _get_remote_size(url, ctx)
    if remote_size is not None:
        projected = current_total_bytes + remote_size
        if projected > max_bytes_allowed:
            raise ValueError(
                f"Download of {expected_name} ({remote_size / (1024*1024):.1f} MB) would exceed "
                f"storage budget ({max_bytes_allowed / (1024*1024*1024):.1f} GB)."
            )

    temp_path = target_path.with_suffix(".tmp")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

    for attempt in range(1, retries + 1):
        try:
            print(f"[{attempt}/{retries}] Connecting to {url} ...")
            start_time = time.time()
            downloaded = 0

            with urllib.request.urlopen(req, context=ctx, timeout=30) as response, temp_path.open("wb") as out_file:
                total_length = response.headers.get("Content-Length")
                total_bytes = int(total_length) if total_length else None

                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)

                    if current_total_bytes + downloaded > max_bytes_allowed:
                        raise ValueError(
                            f"Aborting: Download exceeded maximum storage limit of "
                            f"{max_bytes_allowed / (1024*1024*1024):.1f} GB!"
                        )

                    if total_bytes:
                        pct = (downloaded / total_bytes) * 100
                        mb = downloaded / (1024 * 1024)
                        total_mb = total_bytes / (1024 * 1024)
                        sys.stdout.write(f"\r  Downloaded: {mb:.1f} MB / {total_mb:.1f} MB ({pct:.1f}%)")
                    else:
                        mb = downloaded / (1024 * 1024)
                        sys.stdout.write(f"\r  Downloaded: {mb:.1f} MB")
                    sys.stdout.flush()

            duration = max(time.time() - start_time, 0.01)
            mb_sec = (downloaded / (1024 * 1024)) / duration
            print(f"\n  Finished in {duration:.1f}s ({mb_sec:.2f} MB/s).")

            temp_path.replace(target_path)
            checksum = _compute_sha256(target_path)
            return downloaded, checksum

        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"\n[warn] Attempt {attempt} failed: {exc}", file=sys.stderr)
            if temp_path.exists():
                temp_path.unlink()
            if attempt == retries:
                raise
            time.sleep(2 * attempt)

    raise RuntimeError(f"Failed to download {url} after {retries} attempts.")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.config.exists():
        print(f"[error] Config file not found: {args.config}", file=sys.stderr)
        return 1

    with args.config.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    max_gb = float(cfg.get("dataset", {}).get("max_raw_size_gb", 5.0))
    max_bytes = int(max_gb * 1024 * 1024 * 1024)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.metadata_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = args.metadata_dir / "download_manifest.json"
    manifest: dict[str, Any] = {
        "download_timestamp": datetime.now(UTC).isoformat(),
        "study_region": cfg.get("study_region", {}),
        "files": {},
    }

    if manifest_path.exists():
        try:
            with manifest_path.open("r", encoding="utf-8") as mf:
                existing_manifest = json.load(mf)
                manifest["files"] = existing_manifest.get("files", {})
        except Exception:
            pass

    sources = cfg.get("sources", {})
    if args.source:
        if args.source not in sources:
            print(f"[error] Unknown source '{args.source}'. Available: {list(sources.keys())}", file=sys.stderr)
            return 1
        sources = {args.source: sources[args.source]}

    # Check total size of existing raw files
    current_raw_bytes = sum(f.stat().st_size for f in args.output_dir.glob("*") if f.is_file())
    print(f"Current raw directory size: {current_raw_bytes / (1024 * 1024):.2f} MB")
    print(f"Hard budget limit: {max_gb:.1f} GB")

    success_count = 0
    total_requested = len([s for s in sources.values() if s.get("enabled", True)])

    for key, spec in sources.items():
        if not spec.get("enabled", True):
            continue

        filename = spec.get("filename", f"{key}.csv")
        target_path = args.output_dir / filename
        download_url = spec["download_url"]
        name = spec.get("name", key)

        print("\n" + "=" * 70)
        print(f"Dataset: {name}")
        print(f"Source URL: {spec.get('official_url')}")
        print(f"Download URL: {download_url}")
        print(f"Target: {target_path}")

        if target_path.exists() and not args.force:
            size = target_path.stat().st_size
            print(f"  [cached] File already exists ({size / (1024 * 1024):.2f} MB). Skipping download.")
            checksum = _compute_sha256(target_path)
            manifest["files"][key] = {
                "name": name,
                "publisher": spec.get("publisher"),
                "official_url": spec.get("official_url"),
                "download_url": download_url,
                "local_path": str(target_path.relative_to(REPO_ROOT)),
                "size_bytes": size,
                "sha256": checksum,
                "status": "cached",
                "last_checked": datetime.now(UTC).isoformat(),
            }
            success_count += 1
            continue

        try:
            downloaded_bytes, checksum = download_file(
                url=download_url,
                target_path=target_path,
                expected_name=name,
                max_bytes_allowed=max_bytes,
                current_total_bytes=current_raw_bytes,
                chunk_size=args.chunk_size,
            )
            current_raw_bytes += downloaded_bytes
            manifest["files"][key] = {
                "name": name,
                "publisher": spec.get("publisher"),
                "official_url": spec.get("official_url"),
                "download_url": download_url,
                "local_path": str(target_path.relative_to(REPO_ROOT)),
                "size_bytes": downloaded_bytes,
                "sha256": checksum,
                "status": "downloaded",
                "downloaded_at": datetime.now(UTC).isoformat(),
            }
            success_count += 1
        except Exception as exc:
            print(f"[error] Failed to download {name}: {exc}", file=sys.stderr)
            manifest["files"][key] = {
                "name": name,
                "error": str(exc),
                "status": "failed",
                "attempted_at": datetime.now(UTC).isoformat(),
            }

    # Save manifest
    with manifest_path.open("w", encoding="utf-8") as mf:
        json.dump(manifest, mf, indent=2)
    print(f"\nManifest saved to: {manifest_path}")

    final_total_raw = sum(f.stat().st_size for f in args.output_dir.glob("*") if f.is_file())
    print("\n" + "=" * 70)
    print(f"Download Summary: {success_count}/{total_requested} datasets ready.")
    print(f"Total raw data size: {final_total_raw / (1024 * 1024):.2f} MB")
    if final_total_raw > max_bytes:
        print(f"[ERROR] Raw data exceeds budget limit of {max_gb:.1f} GB!", file=sys.stderr)
        return 1
    if final_total_raw > 1024 * 1024 * 1024:
        print("[WARN] Raw data exceeds preferred target of 1 GB (under 5 GB max).")
    else:
        print("[OK] Dataset size is well within the preferred <= 1 GB target.")

    return 0 if success_count > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
