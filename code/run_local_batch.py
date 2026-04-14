#!/usr/bin/env python3
"""
Parallel local CAD-Steps export pipeline.

Processes DeepCAD JSON files in parallel using OpenCascade (CadQuery/OCP).
No Onshape API required - everything runs locally.

Usage:
    # Process 200 models with 8 workers
    python3 run_local_batch.py --count 200 --workers 8

    # Process all models in a specific bucket
    python3 run_local_batch.py --bucket 0000 --workers 10

    # Process everything
    python3 run_local_batch.py --all --workers 10
"""

import os
import sys
import json
import time
import glob
import argparse
import signal
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from threading import Lock

sys.path.insert(0, os.path.dirname(__file__))
from local_export import process_json_file


def collect_json_files(data_dir, bucket=None, max_count=None):
    """Collect JSON file paths from the DeepCAD data directory."""
    if bucket:
        dirs = [os.path.join(data_dir, bucket)]
    else:
        dirs = sorted(glob.glob(os.path.join(data_dir, '[0-9][0-9][0-9][0-9]')))
    
    files = []
    for d in dirs:
        jsons = sorted(glob.glob(os.path.join(d, '*.json')))
        files.extend(jsons)
        if max_count and len(files) >= max_count:
            break
    
    if max_count:
        files = files[:max_count]
    
    return files


def worker_fn(args):
    """Worker function for parallel processing."""
    json_path, output_dir = args
    # Suppress OCC output by redirecting stderr
    import io
    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    try:
        result = process_json_file(json_path, output_dir, quiet=True)
    finally:
        sys.stderr = old_stderr
    return result


def main():
    parser = argparse.ArgumentParser(description='Parallel local CAD-Steps batch export')
    parser.add_argument('--count', type=int, default=200, help='Number of models to process')
    parser.add_argument('--workers', type=int, default=8, help='Number of parallel workers')
    parser.add_argument('--bucket', type=str, default=None, help='Specific bucket (e.g. 0000)')
    parser.add_argument('--all', action='store_true', help='Process all models')
    parser.add_argument('--output', type=str, default=None, help='Output directory')
    parser.add_argument('--data-dir', type=str, default=None, help='DeepCAD JSON data directory')
    args = parser.parse_args()
    
    project_root = os.path.join(os.path.dirname(__file__), '..')
    data_dir = args.data_dir or os.path.join(project_root, 'data', 'deepcad_raw', 'data', 'cad_json')
    output_dir = args.output or os.path.join(project_root, 'data', 'cad_steps_output')
    
    if not os.path.exists(data_dir):
        print(f"Data directory not found: {data_dir}")
        print("Download: curl -L http://www.cs.columbia.edu/cg/deepcad/data.tar | tar x")
        return
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Collect files
    max_count = None if args.all else args.count
    json_files = collect_json_files(data_dir, bucket=args.bucket, max_count=max_count)
    print(f"Found {len(json_files)} JSON files to process")
    
    # Check what's already done
    done_count = 0
    pending_files = []
    for jf in json_files:
        data_id = os.path.splitext(os.path.basename(jf))[0]
        meta_path = os.path.join(output_dir, data_id, 'metadata.json')
        if os.path.exists(meta_path):
            done_count += 1
        else:
            pending_files.append(jf)
    
    if done_count:
        print(f"Already done: {done_count}, pending: {len(pending_files)}")
    
    if not pending_files:
        print("Nothing to process!")
        return
    
    # Prepare work items
    work_items = [(jf, output_dir) for jf in pending_files]
    
    # Run
    total = len(work_items)
    completed = 0
    succeeded = 0
    failed = 0
    total_files = 0
    total_size_kb = 0
    
    batch_start = time.time()
    
    print(f"\n{'='*70}")
    print(f"CAD-Steps Local Batch Export")
    print(f"  Models: {total} | Workers: {args.workers}")
    print(f"  Output: {output_dir}")
    print(f"{'='*70}\n")
    
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(worker_fn, item): item for item in work_items}
        
        for future in as_completed(futures):
            completed += 1
            try:
                result = future.result()
                if result['status'] == 'success':
                    succeeded += 1
                    total_files += result.get('step_files', 0)
                    total_size_kb += result.get('total_size_kb', 0)
                    icon = '✓'
                else:
                    failed += 1
                    icon = '✗'
                
                elapsed = time.time() - batch_start
                rate = completed / elapsed * 60  # models/min
                eta_s = (total - completed) / (completed / elapsed) if completed else 0
                
                if completed % 50 == 0 or completed == total:
                    print(f"  [{completed}/{total}] ✓{succeeded} ✗{failed} | "
                          f"{rate:.0f}/min | "
                          f"files:{total_files} size:{total_size_kb/1024:.1f}MB | "
                          f"ETA:{eta_s:.0f}s")
                    
            except Exception as e:
                failed += 1
                if completed % 50 == 0:
                    print(f"  [{completed}/{total}] Exception: {e}")
    
    total_time = time.time() - batch_start
    
    # Summary
    print(f"\n{'='*70}")
    print(f"BATCH COMPLETE")
    print(f"{'='*70}")
    print(f"Time: {total_time:.1f}s ({total_time/60:.1f} min)")
    print(f"Processed: {completed}")
    print(f"  ✓ Success: {succeeded} ({succeeded/completed*100:.1f}%)")
    print(f"  ✗ Failed: {failed}")
    print(f"  STEP files: {total_files}")
    print(f"  Total size: {total_size_kb/1024:.1f} MB")
    
    if succeeded:
        avg_time = total_time / succeeded
        avg_files = total_files / succeeded
        avg_size = total_size_kb / succeeded
        
        print(f"\nPer-model averages:")
        print(f"  Time: {avg_time*1000:.0f}ms")
        print(f"  STEP files: {avg_files:.1f}")
        print(f"  Size: {avg_size:.0f} KB")
        
        # Full dataset projection
        total_deepcad = 178238
        est_time_s = avg_time * total_deepcad / args.workers
        est_size_gb = avg_size * total_deepcad / 1024 / 1024
        print(f"\n  --- Full Dataset ({total_deepcad:,} models) ---")
        print(f"  With {args.workers} workers: {est_time_s:.0f}s ({est_time_s/60:.1f} min)")
        print(f"  Estimated size: {est_size_gb:.1f} GB")
        print(f"  Estimated files: {int(avg_files * total_deepcad):,}")
    
    # Save batch results
    results_path = os.path.join(output_dir, 'batch_results.json')
    with open(results_path, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'total': completed,
            'succeeded': succeeded,
            'failed': failed,
            'total_files': total_files,
            'total_size_kb': total_size_kb,
            'total_time': total_time,
            'workers': args.workers,
        }, f, indent=2)


if __name__ == '__main__':
    main()
