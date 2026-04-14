#!/usr/bin/env python3
"""
Parallel batch runner for CAD-Steps dataset extraction.

Processes models from ABC/DeepCAD link files using multiple worker threads.
Each worker gets its own Onshape API client instance.

KEY INSIGHT: Onshape free tier has ~1000 API calls per rolling window.
Each model export uses ~15-25 API calls (copy, rollback, translate, download, cleanup).
Filtered models cost only 1 call. 404 models cost 1 call.

With a budget of 1000 calls:
  - ~60% of ABC models get filtered (1 call each) = ~600 calls for 600 models
  - Remaining ~400 calls = ~20 successful exports

Strategy: Use a global rate limiter (token bucket) to stay under the limit.
Run with 3 workers max to avoid overwhelming the API.

Usage:
    python3 run_parallel_batch.py --link_file ../data/abc_links/objects_0000.yml \\
        --output_dir ../data/batch_200 --limit 200 --workers 3

    # Slower but safer:
    python3 run_parallel_batch.py --link_file ../data/abc_links/objects_0000.yml \\
        --output_dir ../data/batch_200 --limit 200 --workers 2 --delay 1.0
"""

import os
import sys
import json
import time
import yaml
import signal
import argparse
import traceback
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from onshape_api.client import Client
from export_steps import export_all_states, parse_onshape_url, get_feature_list

SUPPORTED_FEATURES = {'newSketch', 'extrude'}

shutdown_event = threading.Event()


def signal_handler(sig, frame):
    print("\n⚠ Shutdown requested. Finishing current models...", flush=True)
    shutdown_event.set()

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


class RateLimiter:
    """
    Thread-safe rate limiter using a token bucket.
    
    Onshape free tier: ~1000 requests per day (rolling 24h window).
    We target 10 requests/minute max to stay safe.
    """
    def __init__(self, calls_per_second=0.5, burst=3):
        self.lock = threading.Lock()
        self.calls_per_second = calls_per_second
        self.burst = burst
        self.tokens = burst
        self.last_refill = time.time()
        self.total_calls = 0

    def acquire(self):
        """Block until a token is available."""
        while True:
            with self.lock:
                now = time.time()
                elapsed = now - self.last_refill
                self.tokens = min(self.burst, self.tokens + elapsed * self.calls_per_second)
                self.last_refill = now
                
                if self.tokens >= 1:
                    self.tokens -= 1
                    self.total_calls += 1
                    return
            
            time.sleep(0.5)


class ThrottledClient(Client):
    """
    Onshape client with global rate limiting and 429 retry.
    """
    _rate_limiter = None
    _rate_limiter_lock = threading.Lock()
    
    @classmethod
    def set_rate_limiter(cls, limiter):
        cls._rate_limiter = limiter

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    def _throttled_request(self, original_method, *args, **kwargs):
        """Wrap API requests with rate limiting and retry logic."""
        max_retries = 3
        for attempt in range(max_retries):
            if ThrottledClient._rate_limiter:
                ThrottledClient._rate_limiter.acquire()
            
            result = original_method(*args, **kwargs)
            
            if hasattr(result, 'status_code') and result.status_code == 429:
                retry_after = int(result.headers.get('Retry-After', 60))
                # Cap retry wait to 5 minutes
                wait_time = min(retry_after, 300)
                if attempt < max_retries - 1:
                    print(f"    ⏳ Rate limited, waiting {wait_time}s (attempt {attempt+1}/{max_retries})...", flush=True)
                    time.sleep(wait_time)
                    continue
            
            return result
        
        return result  # Return last result even if still 429


def process_one_model(data_id, url, output_base, creds_path, 
                      filter_features=True, inter_step_delay=1.5):
    """
    Process a single model with rate limiting awareness.
    """
    if shutdown_event.is_set():
        return {'data_id': data_id, 'url': url, 'status': 'shutdown', 'time_seconds': 0}

    model_dir = os.path.join(output_base, data_id)
    result = {'data_id': data_id, 'url': url, 'status': 'unknown'}
    model_start = time.time()

    # Check if already done
    meta_path = os.path.join(model_dir, 'metadata.json')
    if os.path.exists(meta_path):
        result['status'] = 'already_done'
        result['time_seconds'] = 0
        return result

    try:
        client = Client(creds=creds_path, logging=False)
    except Exception as e:
        result['status'] = 'error'
        result['error'] = f'Client init: {str(e)[:150]}'
        result['time_seconds'] = round(time.time() - model_start, 1)
        return result

    # Step 1: Pre-filter (1 API call)
    try:
        did, wid, eid = parse_onshape_url(url)

        # Rate limit aware: wait before API call
        if ThrottledClient._rate_limiter:
            ThrottledClient._rate_limiter.acquire()

        features_res = client.get_features(did, wid, eid)
        
        if features_res.status_code == 429:
            retry_after = int(features_res.headers.get('Retry-After', 60))
            result['status'] = 'rate_limited'
            result['retry_after'] = retry_after
            result['time_seconds'] = round(time.time() - model_start, 1)
            return result
        
        if features_res.status_code == 404:
            result['status'] = 'api_error_404'
            result['time_seconds'] = round(time.time() - model_start, 1)
            return result
            
        if features_res.status_code != 200:
            result['status'] = 'api_error'
            result['error'] = f'HTTP {features_res.status_code}'
            result['time_seconds'] = round(time.time() - model_start, 1)
            return result

        data = features_res.json()
        features = []
        for feat in data.get('features', []):
            msg = feat.get('message', {})
            features.append({
                'featureId': msg.get('featureId'),
                'featureType': msg.get('featureType'),
                'name': msg.get('name'),
            })

        if not features:
            result['status'] = 'no_features'
            result['time_seconds'] = round(time.time() - model_start, 1)
            return result

        feature_types = set(f['featureType'] for f in features)
        result['feature_count'] = len(features)
        result['feature_types'] = list(feature_types)

        if filter_features and not feature_types.issubset(SUPPORTED_FEATURES):
            unsupported = feature_types - SUPPORTED_FEATURES
            result['status'] = 'skipped_features'
            result['unsupported'] = list(unsupported)
            result['time_seconds'] = round(time.time() - model_start, 1)
            return result

    except Exception as e:
        error_str = str(e)[:200]
        result['status'] = 'api_error' if '404' in error_str else 'error'
        result['error'] = error_str
        result['time_seconds'] = round(time.time() - model_start, 1)
        return result

    # Step 2: Full export (many API calls)
    if shutdown_event.is_set():
        result['status'] = 'shutdown'
        result['time_seconds'] = round(time.time() - model_start, 1)
        return result

    try:
        metadata = export_all_states(
            client, url,
            output_dir=model_dir,
            skip_sketches=True,
            cleanup=True
        )

        if metadata is None:
            result['status'] = 'export_failed'
            result['error'] = 'export_all_states returned None'
        else:
            exported = sum(1 for s in metadata.get('states', []) if s.get('exported'))
            total_states = len(metadata.get('states', []))
            step_files = [f for f in os.listdir(model_dir) if f.endswith('.step')] if os.path.exists(model_dir) else []
            total_size = sum(os.path.getsize(os.path.join(model_dir, f)) for f in step_files)

            result['status'] = 'success'
            result['states_exported'] = exported
            result['states_total'] = total_states
            result['step_files'] = len(step_files)
            result['total_size_kb'] = round(total_size / 1024, 1)

    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)[:200]

    result['time_seconds'] = round(time.time() - model_start, 1)
    
    # Delay between models to be gentle to the API
    time.sleep(inter_step_delay)
    
    return result


def load_models(link_files, limit=None, offset=0):
    """Load model links from YAML files."""
    models = {}
    for lf in link_files:
        with open(lf) as f:
            data = yaml.safe_load(f)
            if data:
                models.update(data)

    sorted_items = sorted(models.items(), key=lambda x: x[0])
    if offset > 0:
        sorted_items = sorted_items[offset:]
    if limit is not None:
        sorted_items = sorted_items[:limit]

    return dict(sorted_items)


def main():
    parser = argparse.ArgumentParser(description="Parallel CAD-Steps batch runner")
    parser.add_argument("--link_file", type=str, nargs='+', required=True)
    parser.add_argument("--output_dir", type=str, required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--creds", type=str, default=None)
    parser.add_argument("--no-filter", action="store_true")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Delay between API calls in seconds (default: 2.0)")
    parser.add_argument("--rate", type=float, default=0.4,
                        help="Max API calls per second across all workers (default: 0.4)")
    args = parser.parse_args()

    # Resolve creds
    creds_path = args.creds
    if creds_path is None:
        for c in ['./creds.json', os.path.join(os.path.dirname(__file__), 'creds.json')]:
            if os.path.exists(c):
                creds_path = os.path.abspath(c)
                break
    if not creds_path or not os.path.exists(creds_path):
        print("ERROR: creds.json not found")
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    # Set up global rate limiter
    rate_limiter = RateLimiter(calls_per_second=args.rate, burst=2)
    ThrottledClient.set_rate_limiter(rate_limiter)

    # Load models
    models = load_models(args.link_file, limit=args.limit, offset=args.offset)
    already_done = sum(1 for d in models if os.path.exists(os.path.join(args.output_dir, d, 'metadata.json')))

    print(f"{'='*70}")
    print(f"CAD-Steps Parallel Batch Export")
    print(f"  Models: {len(models)} (already done: {already_done})")
    print(f"  Workers: {args.workers}")
    print(f"  Rate limit: {args.rate} calls/s, delay: {args.delay}s")
    print(f"  Output: {args.output_dir}")
    print(f"  Filter: {'OFF' if args.no_filter else 'sketch+extrude only'}")
    print(f"{'='*70}\n")

    # Stats
    start_time = time.time()
    results = []
    counts = {'success': 0, 'skipped_features': 0, 'api_error_404': 0, 
              'api_error': 0, 'export_failed': 0, 'error': 0, 
              'already_done': 0, 'rate_limited': 0, 'no_features': 0, 'shutdown': 0}
    stats_lock = threading.Lock()

    filter_features = not args.no_filter

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for data_id, url in models.items():
            if shutdown_event.is_set():
                break
            future = executor.submit(
                process_one_model,
                data_id, url, args.output_dir, creds_path, filter_features, args.delay
            )
            futures[future] = data_id
            # Stagger submission slightly to avoid burst
            time.sleep(0.3)

        done_count = 0
        total = len(futures)
        
        for future in as_completed(futures):
            if shutdown_event.is_set():
                for f in futures:
                    f.cancel()
                break

            data_id = futures[future]
            try:
                result = future.result(timeout=600)
            except Exception as e:
                result = {'data_id': data_id, 'status': 'error', 
                          'error': str(e)[:200], 'time_seconds': 0}

            done_count += 1
            status = result.get('status', 'unknown')
            
            with stats_lock:
                results.append(result)
                if status in counts:
                    counts[status] += 1

            # Progress
            elapsed = time.time() - start_time
            t = result.get('time_seconds', 0)

            if status == 'success':
                files = result.get('step_files', 0)
                size = result.get('total_size_kb', 0)
                print(f"  ✓ [{done_count}/{total}] {data_id}: {files} files, "
                      f"{size:.0f}KB ({t:.0f}s) | "
                      f"✓{counts['success']} ⊘{counts['skipped_features']} ✗{counts['api_error_404']}", flush=True)
            elif status == 'skipped_features':
                unsupported = result.get('unsupported', [])[:3]
                print(f"  ⊘ [{done_count}/{total}] {data_id}: "
                      f"filtered ({', '.join(unsupported)})", flush=True)
            elif status == 'api_error_404':
                print(f"  ✗ [{done_count}/{total}] {data_id}: 404 deleted", flush=True)
            elif status == 'already_done':
                pass  # silent
            elif status == 'rate_limited':
                print(f"  ⏳ [{done_count}/{total}] {data_id}: "
                      f"RATE LIMITED (retry_after={result.get('retry_after', '?')}s)", flush=True)
            elif status != 'shutdown':
                err = result.get('error', '')[:60]
                print(f"  ✗ [{done_count}/{total}] {data_id}: {status} - {err}", flush=True)

            # Periodic summary every 50 models
            if done_count % 50 == 0 and done_count > 0:
                rate = done_count / elapsed if elapsed > 0 else 0
                eta = (total - done_count) / rate / 60 if rate > 0 else float('inf')
                print(f"\n  --- {done_count}/{total} done | "
                      f"✓{counts['success']} ⊘{counts['skipped_features']} "
                      f"404:{counts['api_error_404']} err:{counts['error']} | "
                      f"ETA: {eta:.0f}min ---\n", flush=True)

    # Final summary
    elapsed = time.time() - start_time
    successful = [r for r in results if r['status'] == 'success']
    
    summary = {
        'timestamp': datetime.now().isoformat(),
        'total_models': len(results),
        'elapsed_seconds': round(elapsed, 1),
        'elapsed_minutes': round(elapsed / 60, 1),
        'counts': counts,
        'workers': args.workers,
        'rate_limit': args.rate,
        'delay': args.delay,
    }

    if successful:
        times = [r['time_seconds'] for r in successful]
        summary['success_stats'] = {
            'count': len(successful),
            'avg_time': round(sum(times) / len(times), 1),
            'total_step_files': sum(r.get('step_files', 0) for r in successful),
            'total_size_kb': round(sum(r.get('total_size_kb', 0) for r in successful), 1),
            'total_size_mb': round(sum(r.get('total_size_kb', 0) for r in successful) / 1024, 1),
            'total_states': sum(r.get('states_exported', 0) for r in successful),
            'avg_states': round(sum(r.get('states_exported', 0) for r in successful) / len(successful), 1),
            'avg_files_per_model': round(sum(r.get('step_files', 0) for r in successful) / len(successful), 1),
        }

        # Projections for 500K ABC models
        total_processed = len(results) - counts.get('already_done', 0)
        if total_processed > 0:
            api_error_rate = counts.get('api_error_404', 0) / total_processed
            filter_rate = counts.get('skipped_features', 0) / total_processed
            valid = total_processed - counts.get('api_error_404', 0) - counts.get('skipped_features', 0) - counts.get('api_error', 0) - counts.get('no_features', 0)
            success_of_valid = counts['success'] / valid if valid > 0 else 0

            summary['projections_500k'] = {
                'api_error_rate_pct': round(api_error_rate * 100, 1),
                'filter_rate_pct': round(filter_rate * 100, 1),
                'success_of_valid_pct': round(success_of_valid * 100, 1),
                'est_valid_models': int(500000 * (1 - api_error_rate - filter_rate)),
                'est_successful': int(500000 * (1 - api_error_rate - filter_rate) * success_of_valid),
                'est_api_calls': int(500000 * (api_error_rate + filter_rate) + 
                                     500000 * (1 - api_error_rate - filter_rate) * success_of_valid * 20),
                'est_total_size_gb': round(
                    summary['success_stats']['total_size_mb'] / len(successful) * 
                    int(500000 * (1 - api_error_rate - filter_rate) * success_of_valid) / 1024, 1
                ) if successful else 0,
            }

    report_path = os.path.join(args.output_dir, 'batch_results.json')
    with open(report_path, 'w') as f:
        json.dump({'summary': summary, 'results': results}, f, indent=2)

    print(f"\n{'='*70}")
    print("BATCH COMPLETE")
    print(f"{'='*70}")
    print(f"Time: {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"\nResults:")
    for status, count in sorted(counts.items(), key=lambda x: -x[1]):
        if count > 0:
            print(f"  {status}: {count}")

    if successful:
        ss = summary['success_stats']
        print(f"\nSuccess stats:")
        print(f"  Models exported: {ss['count']}")
        print(f"  Avg time/model: {ss['avg_time']}s")
        print(f"  Total STEP files: {ss['total_step_files']}")
        print(f"  Total size: {ss['total_size_mb']}MB")
        print(f"  Avg states/model: {ss['avg_states']}")

        if 'projections_500k' in summary:
            p = summary['projections_500k']
            print(f"\n500K Projections:")
            print(f"  Filter rate: {p['filter_rate_pct']}%")
            print(f"  404 rate: {p['api_error_rate_pct']}%")
            print(f"  Est valid/exportable: {p['est_valid_models']}")
            print(f"  Est successful: {p['est_successful']}")
            print(f"  Est size: {p['est_total_size_gb']}GB")

    print(f"\nReport: {report_path}")
    return summary


if __name__ == '__main__':
    main()
