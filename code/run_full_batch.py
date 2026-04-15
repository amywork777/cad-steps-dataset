#!/usr/bin/env python3
"""
Full-scale CAD-Steps local export pipeline.

Processes all 215K DeepCAD JSON files using OpenCascade (OCP).
Writes progress to a log file and checkpoint for resumability.

Uses multiprocessing.Process with kill support for per-model timeouts,
because ProcessPoolExecutor cannot kill hung OCC workers.

Usage:
    python3 run_full_batch.py --workers 8 --output ../data/full_output
    
    # Resume after interruption:
    python3 run_full_batch.py --workers 8 --output ../data/full_output --resume
"""

import os
import sys
import json
import time
import argparse
import signal
import multiprocessing
from datetime import datetime
from multiprocessing import Process, Queue

sys.path.insert(0, os.path.dirname(__file__))

# Per-model timeout in seconds
MODEL_TIMEOUT = 120

# Global flag for graceful shutdown
SHUTDOWN = False

def handle_signal(signum, frame):
    global SHUTDOWN
    SHUTDOWN = True
    print("\n[SIGNAL] Shutting down gracefully...")


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


def worker_process(json_path, output_dir, result_queue):
    """Worker process: process one JSON file with SIGALRM timeout."""
    import io
    
    # Set alarm for timeout
    def alarm_handler(signum, frame):
        raise TimeoutError(f"Model timed out after {MODEL_TIMEOUT}s")
    
    signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(MODEL_TIMEOUT)
    
    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    try:
        from local_export import process_json_file
        result = process_json_file(json_path, output_dir, quiet=True)
    except TimeoutError as e:
        result = {
            'data_id': os.path.splitext(os.path.basename(json_path))[0],
            'status': 'timeout',
            'error': str(e),
        }
    except Exception as e:
        result = {
            'data_id': os.path.splitext(os.path.basename(json_path))[0],
            'status': 'crash',
            'error': str(e)[:200],
        }
    finally:
        signal.alarm(0)  # cancel alarm
        sys.stderr = old_stderr
    
    result_queue.put(result)


def run_with_timeout(json_path, output_dir):
    """Run a single model export in a subprocess with hard kill timeout."""
    result_queue = multiprocessing.Queue()
    proc = Process(target=worker_process, args=(json_path, output_dir, result_queue))
    proc.start()
    proc.join(timeout=MODEL_TIMEOUT + 10)  # give a bit extra beyond SIGALRM
    
    if proc.is_alive():
        # Hard kill the hung process
        proc.kill()
        proc.join(timeout=5)
        data_id = os.path.splitext(os.path.basename(json_path))[0]
        return {
            'data_id': data_id,
            'status': 'killed',
            'error': f'Process killed after {MODEL_TIMEOUT + 10}s',
        }
    
    try:
        return result_queue.get_nowait()
    except:
        data_id = os.path.splitext(os.path.basename(json_path))[0]
        return {
            'data_id': data_id,
            'status': 'crash',
            'error': 'Worker died without returning result',
        }


def worker_loop(task_queue, result_queue, output_dir, worker_id):
    """Long-running worker that processes models from a shared queue."""
    import io
    
    while True:
        try:
            json_path = task_queue.get(timeout=1)
        except:
            break  # queue empty or timeout
        
        if json_path is None:  # poison pill
            break
        
        # Use SIGALRM for timeout within this process
        def alarm_handler(signum, frame):
            raise TimeoutError(f"Model timed out after {MODEL_TIMEOUT}s")
        
        signal.signal(signal.SIGALRM, alarm_handler)
        signal.alarm(MODEL_TIMEOUT)
        
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            from local_export import process_json_file
            result = process_json_file(json_path, output_dir, quiet=True)
        except TimeoutError as e:
            data_id = os.path.splitext(os.path.basename(json_path))[0]
            result = {
                'data_id': data_id,
                'status': 'timeout',
                'error': str(e),
            }
        except Exception as e:
            data_id = os.path.splitext(os.path.basename(json_path))[0]
            result = {
                'data_id': data_id,
                'status': 'crash',
                'error': str(e)[:200],
            }
        finally:
            signal.alarm(0)
            sys.stderr = old_stderr
        
        result_queue.put(result)


def main():
    parser = argparse.ArgumentParser(description='Full-scale CAD-Steps batch export')
    parser.add_argument('--workers', type=int, default=6, help='Parallel workers')
    parser.add_argument('--output', type=str, default=None, help='Output directory')
    parser.add_argument('--data-dir', type=str, default=None, help='DeepCAD JSON directory')
    parser.add_argument('--resume', action='store_true', help='Resume from checkpoint')
    parser.add_argument('--batch-size', type=int, default=500,
                       help='Checkpoint frequency (save every N models)')
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
    total_timeout = 0
    total_step_files = 0
    total_size_kb = 0.0
    batch_start = time.time()

    log = open(log_path, 'a')
    log.write(f"\n--- Run started {datetime.now().isoformat()} ---\n")
    log.write(f"Total: {len(all_files)}, Pending: {len(pending)}, Workers: {args.workers}\n")
    log.write(f"Model timeout: {MODEL_TIMEOUT}s\n")
    log.flush()

    print(f"\n{'='*70}")
    print(f"CAD-Steps Full Batch Export")
    print(f"  Total: {len(all_files)} | Pending: {len(pending)} | Workers: {args.workers}")
    print(f"  Timeout: {MODEL_TIMEOUT}s per model")
    print(f"  Output: {output_dir}")
    print(f"  Checkpoint: {checkpoint_path}")
    print(f"{'='*70}\n")

    # Set up task and result queues
    task_queue = multiprocessing.Queue()
    result_queue = multiprocessing.Queue()
    
    # Fill task queue
    for fp in pending:
        task_queue.put(fp)
    
    # Add poison pills
    for _ in range(args.workers):
        task_queue.put(None)
    
    # Start workers
    workers = []
    for i in range(args.workers):
        p = Process(target=worker_loop, args=(task_queue, result_queue, output_dir, i))
        p.start()
        workers.append(p)
    
    # Collect results
    processed_this_run = 0
    last_checkpoint_count = 0
    
    while processed_this_run < len(pending):
        if SHUTDOWN:
            break
        
        try:
            result = result_queue.get(timeout=MODEL_TIMEOUT + 30)
        except:
            # Check if all workers are dead
            alive = [w for w in workers if w.is_alive()]
            if not alive:
                print("All workers finished or died")
                break
            # Some workers alive but no result - check for stuck workers
            for w in alive:
                if w.is_alive():
                    # Worker is alive but hasn't produced results - give it more time
                    pass
            continue
        
        data_id = result.get('data_id', 'unknown')
        done_ids.add(data_id)
        processed_this_run += 1
        
        status = result.get('status', 'unknown')
        if status == 'success':
            total_succeeded += 1
            nf = result.get('step_files', 0)
            sk = result.get('total_size_kb', 0)
            total_step_files += nf
            total_size_kb += sk
        elif status == 'timeout' or status == 'killed':
            total_timeout += 1
            err = result.get('error', 'unknown')
            log.write(f"TIMEOUT {data_id}: {err}\n")
        else:
            total_failed += 1
            err = result.get('error', 'unknown')
            log.write(f"FAIL {data_id}: {err}\n")
        
        # Checkpoint every N models
        if processed_this_run - last_checkpoint_count >= args.batch_size:
            save_checkpoint(checkpoint_path, done_ids)
            last_checkpoint_count = processed_this_run
        
        # Progress every 100
        if processed_this_run % 100 == 0:
            elapsed = time.time() - batch_start
            rate = processed_this_run / elapsed if elapsed > 0 else 0
            remaining = len(pending) - processed_this_run
            eta = remaining / rate if rate > 0 else 0
            pct = len(done_ids) / len(all_files) * 100
            
            msg = (f"[{len(done_ids)}/{len(all_files)} ({pct:.1f}%)] "
                   f"✓{total_succeeded} ✗{total_failed} ⏱{total_timeout} | "
                   f"{rate:.1f}/s | "
                   f"files:{total_step_files} size:{total_size_kb/1024:.1f}MB | "
                   f"ETA:{eta/60:.0f}min")
            print(msg)
            log.write(msg + "\n")
            log.flush()
    
    # Final checkpoint
    save_checkpoint(checkpoint_path, done_ids)
    
    # Clean up workers
    for w in workers:
        if w.is_alive():
            w.terminate()
            w.join(timeout=5)
            if w.is_alive():
                w.kill()

    # Final summary
    total_time = time.time() - batch_start
    summary = {
        'timestamp': datetime.now().isoformat(),
        'total_files': len(all_files),
        'processed_this_run': processed_this_run,
        'total_done': len(done_ids),
        'succeeded': total_succeeded,
        'failed': total_failed,
        'timeout': total_timeout,
        'step_files': total_step_files,
        'total_size_mb': round(total_size_kb / 1024, 2),
        'total_time_seconds': round(total_time, 1),
        'workers': args.workers,
        'model_timeout': MODEL_TIMEOUT,
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
    print(f"  ⏱ Timeout: {total_timeout}")
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
