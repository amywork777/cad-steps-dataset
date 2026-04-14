#!/usr/bin/env python3
"""
Full-scale CAD-Steps local export pipeline.

Processes all 215K DeepCAD JSON files using OpenCascade (OCP).
Writes progress to a log file and checkpoint for resumability.

Usage:
    python3 run_full_batch.py --workers 8 --output ../data/full_output
    
    # Resume after interruption:
    python3 run_full_batch.py --workers 8 --output ../data/full_output --resume
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

sys.path.insert(0, os.path.dirname(__file__))
from local_export import process_json_file


# Global flag for graceful shutdown
SHUTDOWN = False

def handle_signal(signum, frame):
    global SHUTDOWN
    SHUTDOWN = True
    print("\n[SIGNAL] Shutting down gracefully after current batch...")


def collect_all_json_files(data_dir):
    """Collect all JSON files from all bucket directories."""
    files = []
    for bucket in sorted(os.listdir(data_dir)):
        bucket_dir = os.path.join(data_dir, bucket)
        if not os.path.isdir(bucket_dir):
            continue
        for jf in sorted(os.listdir(bucket_dir)):
            if jf.endswith('.json'):
                files.append(os.path.join(bucket_dir, jf))
    return files


def load_checkpoint(checkpoint_path):
    """Load set of already-processed data IDs."""
    if os.path.exists(checkpoint_path):
        with open(checkpoint_path) as f:
            return set(json.load(f))
    return set()


def save_checkpoint(checkpoint_path, done_ids):
    """Save checkpoint atomically."""
    tmp = checkpoint_path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(sorted(done_ids), f)
    os.replace(tmp, checkpoint_path)


def worker_fn(args):
    """Worker: process one JSON file."""
    json_path, output_dir = args
    import io
    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    try:
        result = process_json_file(json_path, output_dir, quiet=True, compress=True)
    except Exception as e:
        result = {
            'data_id': os.path.splitext(os.path.basename(json_path))[0],
            'status': 'crash',
            'error': str(e)[:200],
        }
    finally:
        sys.stderr = old_stderr
    return result


def main():
    parser = argparse.ArgumentParser(description='Full-scale CAD-Steps batch export')
    parser.add_argument('--workers', type=int, default=6, help='Parallel workers')
    parser.add_argument('--output', type=str, default=None, help='Output directory')
    parser.add_argument('--data-dir', type=str, default=None, help='DeepCAD JSON directory')
    parser.add_argument('--resume', action='store_true', help='Resume from checkpoint')
    parser.add_argument('--batch-size', type=int, default=500,
                       help='Submit this many at a time (for checkpoint frequency)')
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    project_root = os.path.join(os.path.dirname(__file__), '..')
    data_dir = args.data_dir or os.path.join(project_root, 'data', 'deepcad_raw', 'data', 'cad_json')
    output_dir = args.output or os.path.join(project_root, 'data', 'full_output')
    os.makedirs(output_dir, exist_ok=True)

    checkpoint_path = os.path.join(output_dir, 'checkpoint.json')
    log_path = os.path.join(output_dir, 'batch.log')
    stats_path = os.path.join(output_dir, 'batch_stats.json')

    # Collect files
    print(f"Scanning {data_dir}...")
    all_files = collect_all_json_files(data_dir)
    print(f"Total JSON files: {len(all_files)}")

    # Filter already done
    done_ids = load_checkpoint(checkpoint_path) if args.resume else set()
    if done_ids:
        print(f"Resuming: {len(done_ids)} already processed")

    pending = []
    for fp in all_files:
        data_id = os.path.splitext(os.path.basename(fp))[0]
        if data_id not in done_ids:
            pending.append(fp)
    
    print(f"Pending: {len(pending)}")
    if not pending:
        print("Nothing to process!")
        return

    # Stats
    total_succeeded = 0
    total_failed = 0
    total_step_files = 0
    total_size_kb = 0.0
    batch_start = time.time()

    log = open(log_path, 'a')
    log.write(f"\n--- Run started {datetime.now().isoformat()} ---\n")
    log.write(f"Total: {len(all_files)}, Pending: {len(pending)}, Workers: {args.workers}\n")
    log.flush()

    print(f"\n{'='*70}")
    print(f"CAD-Steps Full Batch Export")
    print(f"  Total: {len(all_files)} | Pending: {len(pending)} | Workers: {args.workers}")
    print(f"  Output: {output_dir}")
    print(f"  Checkpoint: {checkpoint_path}")
    print(f"{'='*70}\n")

    # Process in batches for checkpointing
    processed_this_run = 0
    batch_size = args.batch_size
    
    for batch_start_idx in range(0, len(pending), batch_size):
        if SHUTDOWN:
            break
        
        batch = pending[batch_start_idx:batch_start_idx + batch_size]
        work_items = [(fp, output_dir) for fp in batch]
        
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(worker_fn, item): item for item in work_items}
            
            for future in as_completed(futures):
                if SHUTDOWN:
                    break
                
                try:
                    result = future.result(timeout=60)
                    data_id = result.get('data_id', 'unknown')
                    done_ids.add(data_id)
                    processed_this_run += 1
                    
                    if result['status'] == 'success':
                        total_succeeded += 1
                        nf = result.get('step_files', 0)
                        sk = result.get('total_size_kb', 0)
                        total_step_files += nf
                        total_size_kb += sk
                    else:
                        total_failed += 1
                        err = result.get('error', 'unknown')
                        log.write(f"FAIL {data_id}: {err}\n")
                    
                except Exception as e:
                    total_failed += 1
                    log.write(f"EXCEPTION: {e}\n")
                
                # Progress every 500
                if processed_this_run % 500 == 0:
                    elapsed = time.time() - batch_start
                    rate = processed_this_run / elapsed
                    remaining = len(pending) - processed_this_run
                    eta = remaining / rate if rate > 0 else 0
                    pct = (len(done_ids)) / len(all_files) * 100
                    
                    msg = (f"[{len(done_ids)}/{len(all_files)} ({pct:.1f}%)] "
                           f"✓{total_succeeded} ✗{total_failed} | "
                           f"{rate:.0f}/s | "
                           f"files:{total_step_files} size:{total_size_kb/1024:.1f}MB | "
                           f"ETA:{eta:.0f}s ({eta/60:.1f}min)")
                    print(msg)
                    log.write(msg + "\n")
                    log.flush()
        
        # Checkpoint after each batch
        save_checkpoint(checkpoint_path, done_ids)
        
        elapsed = time.time() - batch_start
        msg = f"[Checkpoint] {len(done_ids)} done, {elapsed:.0f}s elapsed"
        print(msg)
        log.write(msg + "\n")
        log.flush()

    # Final summary
    total_time = time.time() - batch_start
    summary = {
        'timestamp': datetime.now().isoformat(),
        'total_files': len(all_files),
        'processed_this_run': processed_this_run,
        'total_done': len(done_ids),
        'succeeded': total_succeeded,
        'failed': total_failed,
        'step_files': total_step_files,
        'total_size_mb': round(total_size_kb / 1024, 2),
        'total_time_seconds': round(total_time, 1),
        'workers': args.workers,
        'models_per_second': round(processed_this_run / total_time, 1) if total_time > 0 else 0,
    }

    with open(stats_path, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*70}")
    print(f"BATCH COMPLETE")
    print(f"{'='*70}")
    print(f"Time: {total_time:.1f}s ({total_time/60:.1f}min)")
    print(f"Processed: {processed_this_run}")
    print(f"  ✓ Success: {total_succeeded}")
    print(f"  ✗ Failed: {total_failed}")
    print(f"  STEP files: {total_step_files}")
    print(f"  Size: {total_size_kb/1024:.1f} MB")
    if processed_this_run > 0:
        print(f"  Rate: {processed_this_run/total_time:.1f} models/sec")
    print(f"\nCheckpoint: {checkpoint_path}")
    print(f"Stats: {stats_path}")
    print(f"Log: {log_path}")

    log.write(f"\n--- Run finished {datetime.now().isoformat()} ---\n")
    log.write(json.dumps(summary, indent=2))
    log.write("\n")
    log.close()


if __name__ == '__main__':
    main()
