#!/usr/bin/env python3
"""Upload CAD-Steps dataset to HuggingFace Hub.

Usage:
    # First time: login with token
    huggingface-cli login --token YOUR_TOKEN
    
    # Create repo and upload everything
    python upload_to_hf.py --create
    
    # Incremental upload (only new models)
    python upload_to_hf.py --incremental
    
    # Upload specific range
    python upload_to_hf.py --start 0 --end 1000
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from huggingface_hub import HfApi, create_repo, upload_folder, CommitOperationAdd


REPO_ID = "amzyst1/cad-steps"
DATA_DIR = Path("/home/kit/cad-steps-dataset/data/full_output")
DATASET_CARD = Path("/home/kit/cad-steps-dataset/DATASET_CARD.md")
BATCH_SIZE = 500  # upload in batches to avoid timeouts


def get_completed_models():
    """Get list of completed model directories."""
    models = []
    for d in sorted(os.listdir(DATA_DIR)):
        dpath = DATA_DIR / d
        if dpath.is_dir() and (dpath / "metadata.json").exists():
            # Verify at least one step file exists
            step_files = list(dpath.glob("state_*.step.gz"))
            if step_files:
                models.append(d)
    return models


def create_hf_repo(api):
    """Create the HuggingFace dataset repository."""
    print(f"Creating repo: {REPO_ID}")
    create_repo(
        repo_id=REPO_ID,
        repo_type="dataset",
        private=False,  # public dataset
        exist_ok=True,
    )
    
    # Upload the dataset card as README.md
    if DATASET_CARD.exists():
        api.upload_file(
            path_or_fileobj=str(DATASET_CARD),
            path_in_repo="README.md",
            repo_id=REPO_ID,
            repo_type="dataset",
            commit_message="Add dataset card",
        )
        print("Uploaded dataset card (README.md)")


def upload_batch(api, models, batch_num, total_batches):
    """Upload a batch of models using commit operations."""
    operations = []
    for model_id in models:
        model_dir = DATA_DIR / model_id
        for f in sorted(os.listdir(model_dir)):
            fpath = model_dir / f
            if fpath.is_file():
                operations.append(
                    CommitOperationAdd(
                        path_in_repo=f"data/{model_id}/{f}",
                        path_or_fileobj=str(fpath),
                    )
                )
    
    if not operations:
        return
    
    commit_msg = f"Add models batch {batch_num}/{total_batches} ({len(models)} models)"
    print(f"  Uploading batch {batch_num}/{total_batches}: {len(models)} models, {len(operations)} files...")
    
    retries = 3
    for attempt in range(retries):
        try:
            api.create_commit(
                repo_id=REPO_ID,
                repo_type="dataset",
                operations=operations,
                commit_message=commit_msg,
            )
            print(f"  Batch {batch_num} uploaded successfully!")
            return
        except Exception as e:
            if attempt < retries - 1:
                wait = 30 * (attempt + 1)
                print(f"  Error: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  FAILED batch {batch_num}: {e}")
                raise


def get_uploaded_models(api):
    """Get list of models already uploaded to HuggingFace."""
    try:
        files = api.list_repo_tree(
            repo_id=REPO_ID,
            repo_type="dataset",
            path_in_repo="data",
        )
        uploaded = set()
        for f in files:
            if hasattr(f, 'rfilename'):
                parts = f.rfilename.split("/")
                if len(parts) >= 2:
                    uploaded.add(parts[1])
            elif hasattr(f, 'path'):
                # tree entry (directory)
                dirname = f.path.split("/")[-1]
                uploaded.add(dirname)
        return uploaded
    except Exception:
        return set()


def main():
    parser = argparse.ArgumentParser(description="Upload CAD-Steps to HuggingFace")
    parser.add_argument("--create", action="store_true", help="Create repo and upload dataset card")
    parser.add_argument("--incremental", action="store_true", help="Only upload new models")
    parser.add_argument("--start", type=int, default=0, help="Start index")
    parser.add_argument("--end", type=int, default=-1, help="End index (-1 for all)")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="Models per batch commit")
    parser.add_argument("--dry-run", action="store_true", help="Just print what would be uploaded")
    args = parser.parse_args()
    
    api = HfApi()
    
    # Verify login
    try:
        whoami = api.whoami()
        print(f"Logged in as: {whoami['name']}")
    except Exception:
        print("ERROR: Not logged in. Run: huggingface-cli login --token YOUR_TOKEN")
        sys.exit(1)
    
    if args.create:
        create_hf_repo(api)
    
    # Get models to upload
    all_models = get_completed_models()
    print(f"Found {len(all_models)} completed models locally")
    
    if args.incremental:
        print("Checking already uploaded models...")
        uploaded = get_uploaded_models(api)
        print(f"Already uploaded: {len(uploaded)}")
        models = [m for m in all_models if m not in uploaded]
        print(f"New models to upload: {len(models)}")
    else:
        end = args.end if args.end > 0 else len(all_models)
        models = all_models[args.start:end]
        print(f"Uploading models {args.start} to {args.start + len(models)}")
    
    if not models:
        print("Nothing to upload!")
        return
    
    if args.dry_run:
        print(f"DRY RUN: Would upload {len(models)} models")
        for m in models[:10]:
            print(f"  {m}/")
        if len(models) > 10:
            print(f"  ... and {len(models) - 10} more")
        return
    
    # Upload in batches
    total_batches = (len(models) + args.batch_size - 1) // args.batch_size
    for i in range(0, len(models), args.batch_size):
        batch = models[i:i + args.batch_size]
        batch_num = i // args.batch_size + 1
        upload_batch(api, batch, batch_num, total_batches)
        
        if batch_num < total_batches:
            time.sleep(5)  # small delay between batches
    
    print(f"\nDone! Dataset available at: https://huggingface.co/datasets/{REPO_ID}")


if __name__ == "__main__":
    main()
