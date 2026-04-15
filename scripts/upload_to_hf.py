#!/usr/bin/env python3
"""Upload CAD-Steps dataset to HuggingFace incrementally.

Usage:
    # First time: create repo and upload
    python scripts/upload_to_hf.py --token YOUR_HF_TOKEN

    # Resume/incremental upload (after more models are generated)
    python scripts/upload_to_hf.py --token YOUR_HF_TOKEN --resume

    # Upload specific shard
    python scripts/upload_to_hf.py --token YOUR_HF_TOKEN --shard 0
"""

import argparse
import json
import os
import sys
import tarfile
import tempfile
from pathlib import Path

from huggingface_hub import HfApi, create_repo


REPO_ID = "amzyst1/cad-steps"
DATA_DIR = Path(__file__).parent.parent / "data" / "full_output"
README_PATH = Path(__file__).parent.parent / "HUGGINGFACE_README.md"
SHARD_SIZE = 5000  # models per tar shard
UPLOAD_TRACKER = Path(__file__).parent.parent / ".hf_uploaded.json"


def get_completed_models(data_dir: Path) -> list[str]:
    """Get list of completed model directories (have metadata.json)."""
    models = []
    for d in sorted(os.listdir(data_dir)):
        dpath = data_dir / d
        if dpath.is_dir() and (dpath / "metadata.json").exists():
            models.append(d)
    return models


def load_upload_tracker() -> set:
    """Load set of already-uploaded model IDs."""
    if UPLOAD_TRACKER.exists():
        with open(UPLOAD_TRACKER) as f:
            return set(json.load(f))
    return set()


def save_upload_tracker(uploaded: set):
    """Save set of uploaded model IDs."""
    with open(UPLOAD_TRACKER, "w") as f:
        json.dump(sorted(uploaded), f)


def create_shard_tar(models: list[str], data_dir: Path, shard_idx: int) -> Path:
    """Create a tar.gz archive for a shard of models."""
    tar_path = Path(tempfile.mkdtemp()) / f"shard_{shard_idx:04d}.tar.gz"
    
    with tarfile.open(tar_path, "w:gz") as tar:
        for model_id in models:
            model_dir = data_dir / model_id
            for f in sorted(os.listdir(model_dir)):
                filepath = model_dir / f
                arcname = f"{model_id}/{f}"
                tar.add(filepath, arcname=arcname)
    
    size_mb = tar_path.stat().st_size / 1024 / 1024
    print(f"  Shard {shard_idx}: {len(models)} models, {size_mb:.1f} MB")
    return tar_path


def upload_dataset(token: str, resume: bool = False, specific_shard: int = None):
    api = HfApi(token=token)
    
    # Create repo if it doesn't exist
    try:
        create_repo(
            repo_id=REPO_ID,
            repo_type="dataset",
            token=token,
            exist_ok=True,
        )
        print(f"Repository {REPO_ID} ready")
    except Exception as e:
        print(f"Repo creation: {e}")
    
    # Upload README
    if not resume:
        print("Uploading dataset card...")
        api.upload_file(
            path_or_fileobj=str(README_PATH),
            path_in_repo="README.md",
            repo_id=REPO_ID,
            repo_type="dataset",
            token=token,
        )
        print("  README.md uploaded")
    
    # Get completed models
    all_models = get_completed_models(DATA_DIR)
    print(f"\nTotal completed models: {len(all_models)}")
    
    # Check what's already uploaded
    uploaded = load_upload_tracker() if resume else set()
    if uploaded:
        print(f"Already uploaded: {len(uploaded)} models")
    
    # Filter to un-uploaded models
    to_upload = [m for m in all_models if m not in uploaded]
    if not to_upload:
        print("Nothing new to upload!")
        return
    
    print(f"Models to upload: {len(to_upload)}")
    
    # Split into shards
    shards = []
    for i in range(0, len(to_upload), SHARD_SIZE):
        shards.append(to_upload[i:i + SHARD_SIZE])
    
    print(f"Shards to create: {len(shards)} (up to {SHARD_SIZE} models each)")
    
    # Calculate shard offset (so we don't overwrite existing shards)
    existing_shard_count = len(uploaded) // SHARD_SIZE if uploaded else 0
    
    for i, shard_models in enumerate(shards):
        shard_idx = existing_shard_count + i
        
        if specific_shard is not None and shard_idx != specific_shard:
            continue
        
        print(f"\nProcessing shard {shard_idx}...")
        tar_path = create_shard_tar(shard_models, DATA_DIR, shard_idx)
        
        try:
            print(f"  Uploading shard_{shard_idx:04d}.tar.gz...")
            api.upload_file(
                path_or_fileobj=str(tar_path),
                path_in_repo=f"data/shard_{shard_idx:04d}.tar.gz",
                repo_id=REPO_ID,
                repo_type="dataset",
                token=token,
            )
            print(f"  Shard {shard_idx} uploaded successfully!")
            
            # Track uploaded models
            uploaded.update(shard_models)
            save_upload_tracker(uploaded)
            
        except Exception as e:
            print(f"  ERROR uploading shard {shard_idx}: {e}")
            raise
        finally:
            # Cleanup temp file
            if tar_path.exists():
                tar_path.unlink()
    
    print(f"\nDone! Total uploaded: {len(uploaded)} models")
    print(f"Dataset URL: https://huggingface.co/datasets/{REPO_ID}")


def upload_flat(token: str, resume: bool = False):
    """Alternative: upload individual model folders directly (no tar sharding).
    Better for incremental updates but slower for bulk uploads."""
    api = HfApi(token=token)
    
    # Create repo
    create_repo(
        repo_id=REPO_ID,
        repo_type="dataset",
        token=token,
        exist_ok=True,
    )
    
    # Upload README
    if not resume:
        api.upload_file(
            path_or_fileobj=str(README_PATH),
            path_in_repo="README.md",
            repo_id=REPO_ID,
            repo_type="dataset",
            token=token,
        )
    
    # Upload entire data directory using upload_folder
    print("Uploading data directory...")
    api.upload_folder(
        folder_path=str(DATA_DIR),
        path_in_repo="data",
        repo_id=REPO_ID,
        repo_type="dataset",
        token=token,
        ignore_patterns=["checkpoint.json", "batch.log"],
    )
    print(f"Done! https://huggingface.co/datasets/{REPO_ID}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload CAD-Steps to HuggingFace")
    parser.add_argument("--token", required=True, help="HuggingFace write token")
    parser.add_argument("--resume", action="store_true", help="Resume from previous upload")
    parser.add_argument("--shard", type=int, default=None, help="Upload specific shard only")
    parser.add_argument("--flat", action="store_true", help="Upload flat (no tar sharding)")
    args = parser.parse_args()
    
    if args.flat:
        upload_flat(args.token, args.resume)
    else:
        upload_dataset(args.token, args.resume, args.shard)
