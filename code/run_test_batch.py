#!/usr/bin/env python3
"""
Run the CAD-Steps export pipeline on a test batch of ABC/DeepCAD models.

Tests 15 models from the ABC dataset to measure:
- Success/failure rate
- Time per model
- Common error patterns
- Output sizes

Results are saved to data/test_batch/ with a summary report.
"""

import os
import json
import time
import traceback
import yaml

from onshape_api.client import Client
from export_steps import export_all_states, parse_onshape_url, get_feature_list

# ABC dataset test models (from objects_0000.yml)
# Mix of different documents for variety
TEST_MODELS = {
    # First 3 are the DeepCAD paper's own test examples (known to work)
    '00000352': 'https://cad.onshape.com/documents/4185972a944744d8a7a0f2b4/w/d82d7eef8edf4342b7e49732/e/b6d6b562e8b64e7ea50d8325',
    '00001272': 'https://cad.onshape.com/documents/b53ece83d8964b44bbf1f8ed/w/6b2f1aad3c43402c82009c85/e/91cb13b68f164c2eba845ce6',
    '00001616': 'https://cad.onshape.com/documents/8c3b97c1382c43bab3eb1b48/w/43439c4e192347ecbf818421/e/63b575e3ac654545b571eee6',
    # ABC dataset models (diverse selection)
    '00000000': 'https://cad.onshape.com/documents/290a9120f9f249a7a05cfe9c/w/f3d6fe4cfa4f4fd5a956c1f5/e/f83841055a93404a97c5ae79',
    '00000005': 'https://cad.onshape.com/documents/d4fe04f0f5f84b52bd4f10e4/w/af184e4c3083411ba6f2afac/e/da756952509a495bb53a1aae',
    '00000007': 'https://cad.onshape.com/documents/b33a147f86da49879455d286/w/bfdeeceb44a140cfae14fdd1/e/c26b2860c5d143a6a1414663',
    '00000010': 'https://cad.onshape.com/documents/b4b99d35e04b4277931f9a9c/w/cb0e0369017a4b1c8ec4a8ed/e/44bc1dcea2704499b5b3e091',
    '00000011': 'https://cad.onshape.com/documents/e909f412cda24521865fac0f/w/6f8b499942424a50a940c5f6/e/50bc16864ff74c1280f3d506',
    '00000013': 'https://cad.onshape.com/documents/c2f4d27f35ed4c138caf5c18/w/cfe522a1c8764448925b3c27/e/1194b43616f649a88d7abb19',
    '00000014': 'https://cad.onshape.com/documents/5b1c2f8a8c6f40fdaae1e69d/w/fd9fe684325d4c0bb4d47656/e/5a811e4c224e4813833b8c34',
    '00000036': 'https://cad.onshape.com/documents/b169abf5f2444251b529c688/w/783429fd8e1740c586abf641/e/053658599dc543e58f87d790',
    '00000037': 'https://cad.onshape.com/documents/c7d977f326364e35bb5b5d27/w/6d695530bcd04e278af09570/e/7a18e6ce3c7940c888cc467a',
    '00000046': 'https://cad.onshape.com/documents/1a67c6032bbd479492910b39/w/2e84fdab0d9a425690b11483/e/05b45df32dcc429eb38849a2',
    '00000047': 'https://cad.onshape.com/documents/1a67c6032bbd479492910b39/w/2e84fdab0d9a425690b11483/e/4d0b2ace97de47caa902a709',
    '00000035': 'https://cad.onshape.com/documents/6763f7e2f51a489caaf599f0/w/ae197a317c12480fbb17ca09/e/8c9312980b444a2c8770cee3',
}


def pre_filter(client, data_id, url):
    """
    Quick check: does this model have sketch+extrude features only?
    Returns (True, feature_count) if suitable, (False, reason) if not.
    """
    try:
        did, wid, eid = parse_onshape_url(url)
        features = get_feature_list(client, did, wid, eid)
        
        if not features:
            return False, "no_features"
        
        feature_types = set(f['featureType'] for f in features)
        unsupported = feature_types - {'newSketch', 'extrude'}
        
        if unsupported:
            return False, f"unsupported_types:{','.join(unsupported)}"
        
        return True, len(features)
    except Exception as e:
        return False, f"error:{str(e)[:100]}"


def run_batch():
    """Run the full batch test."""
    output_base = os.path.join(os.path.dirname(__file__), '..', 'data', 'test_batch')
    os.makedirs(output_base, exist_ok=True)
    
    client = Client(creds='./creds.json', logging=False)
    
    results = []
    total_start = time.time()
    
    print("=" * 70)
    print("CAD-Steps Dataset - Test Batch Run")
    print(f"Models to process: {len(TEST_MODELS)}")
    print("=" * 70)
    
    for i, (data_id, url) in enumerate(TEST_MODELS.items()):
        print(f"\n[{i+1}/{len(TEST_MODELS)}] Model {data_id}")
        print(f"  URL: {url}")
        
        model_start = time.time()
        result = {
            'data_id': data_id,
            'url': url,
            'status': 'unknown',
        }
        
        # Step 1: Pre-filter
        print(f"  Pre-filtering...")
        suitable, info = pre_filter(client, data_id, url)
        
        if not suitable:
            print(f"  ✗ Skipped: {info}")
            result['status'] = 'filtered'
            result['filter_reason'] = str(info)
            result['time_seconds'] = time.time() - model_start
            results.append(result)
            continue
        
        print(f"  ✓ {info} features (sketch+extrude only)")
        result['feature_count'] = info
        
        # Step 2: Run full export
        model_dir = os.path.join(output_base, data_id)
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
                # Count successful exports
                exported = sum(1 for s in metadata.get('states', []) if s.get('exported'))
                total_states = len(metadata.get('states', []))
                
                # Measure output sizes
                step_files = [f for f in os.listdir(model_dir) if f.endswith('.step')]
                total_size = sum(os.path.getsize(os.path.join(model_dir, f)) for f in step_files)
                
                result['status'] = 'success'
                result['states_exported'] = exported
                result['states_total'] = total_states
                result['step_files'] = len(step_files)
                result['total_size_kb'] = round(total_size / 1024, 1)
                
                print(f"  ✓ Exported {exported}/{total_states} states, {len(step_files)} STEP files, {result['total_size_kb']:.1f} KB total")
        
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)[:200]
            result['traceback'] = traceback.format_exc()[-500:]
            print(f"  ✗ Error: {e}")
        
        result['time_seconds'] = round(time.time() - model_start, 1)
        print(f"  Time: {result['time_seconds']}s")
        results.append(result)
        
        # Small delay between models to be nice to the API
        time.sleep(2)
    
    total_time = round(time.time() - total_start, 1)
    
    # Generate summary
    summary = generate_summary(results, total_time)
    
    # Save results
    results_path = os.path.join(output_base, 'batch_results.json')
    with open(results_path, 'w') as f:
        json.dump({'results': results, 'summary': summary}, f, indent=2)
    
    summary_path = os.path.join(output_base, 'REPORT.md')
    with open(summary_path, 'w') as f:
        f.write(format_report(results, summary, total_time))
    
    print(f"\n{'=' * 70}")
    print("BATCH COMPLETE")
    print(f"{'=' * 70}")
    print(f"Total time: {total_time}s ({total_time/60:.1f} min)")
    print(f"Results: {results_path}")
    print(f"Report: {summary_path}")
    
    # Print summary
    print(f"\nSucceeded: {summary['succeeded']}")
    print(f"Filtered: {summary['filtered']}")
    print(f"Failed: {summary['failed']}")
    print(f"Errored: {summary['errored']}")
    
    if summary['succeeded'] > 0:
        print(f"\nAvg time per successful model: {summary['avg_time_success']:.1f}s")
        print(f"Total STEP files: {summary['total_step_files']}")
        print(f"Total output size: {summary['total_output_kb']:.1f} KB")
        
        # Estimate for full 178k run
        est_hours = (summary['avg_time_success'] * 178000) / 3600
        print(f"\n--- Full Run Estimate (178k models) ---")
        print(f"Assuming {summary['success_rate']:.0f}% success rate:")
        print(f"  Sequential: ~{est_hours:.0f} hours ({est_hours/24:.0f} days)")
        print(f"  10 parallel: ~{est_hours/10:.0f} hours ({est_hours/10/24:.0f} days)")
    
    return results, summary


def generate_summary(results, total_time):
    succeeded = [r for r in results if r['status'] == 'success']
    filtered = [r for r in results if r['status'] == 'filtered']
    failed = [r for r in results if r['status'] == 'export_failed']
    errored = [r for r in results if r['status'] == 'error']
    
    summary = {
        'total_models': len(results),
        'succeeded': len(succeeded),
        'filtered': len(filtered),
        'failed': len(failed),
        'errored': len(errored),
        'total_time_seconds': total_time,
        'success_rate': (len(succeeded) / len(results) * 100) if results else 0,
    }
    
    if succeeded:
        times = [r['time_seconds'] for r in succeeded]
        summary['avg_time_success'] = sum(times) / len(times)
        summary['min_time_success'] = min(times)
        summary['max_time_success'] = max(times)
        summary['total_step_files'] = sum(r.get('step_files', 0) for r in succeeded)
        summary['total_output_kb'] = sum(r.get('total_size_kb', 0) for r in succeeded)
        summary['total_states_exported'] = sum(r.get('states_exported', 0) for r in succeeded)
    
    if filtered:
        filter_reasons = {}
        for r in filtered:
            reason = r.get('filter_reason', 'unknown')
            # Group by type
            key = reason.split(':')[0] if ':' in reason else reason
            filter_reasons[key] = filter_reasons.get(key, 0) + 1
        summary['filter_reasons'] = filter_reasons
    
    return summary


def format_report(results, summary, total_time):
    lines = [
        "# CAD-Steps Test Batch Report",
        "",
        f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Total time:** {total_time}s ({total_time/60:.1f} min)",
        f"**Models tested:** {summary['total_models']}",
        "",
        "## Results Summary",
        "",
        f"| Status | Count |",
        f"|--------|-------|",
        f"| ✓ Success | {summary['succeeded']} |",
        f"| ⊘ Filtered | {summary['filtered']} |",
        f"| ✗ Export Failed | {summary['failed']} |",
        f"| ✗ Error | {summary['errored']} |",
        "",
    ]
    
    if summary.get('avg_time_success'):
        lines.extend([
            "## Performance",
            "",
            f"- Avg time per success: {summary['avg_time_success']:.1f}s",
            f"- Min/Max: {summary.get('min_time_success', 0):.1f}s / {summary.get('max_time_success', 0):.1f}s",
            f"- Total STEP files generated: {summary.get('total_step_files', 0)}",
            f"- Total output size: {summary.get('total_output_kb', 0):.1f} KB",
            f"- Total states exported: {summary.get('total_states_exported', 0)}",
            "",
        ])
    
    if summary.get('filter_reasons'):
        lines.extend([
            "## Filter Reasons",
            "",
        ])
        for reason, count in summary['filter_reasons'].items():
            lines.append(f"- {reason}: {count}")
        lines.append("")
    
    lines.extend([
        "## Model Details",
        "",
        "| ID | Status | Features | States Exported | Time (s) | Size (KB) |",
        "|----|--------|----------|-----------------|----------|-----------|",
    ])
    
    for r in results:
        status = '✓' if r['status'] == 'success' else ('⊘' if r['status'] == 'filtered' else '✗')
        features = r.get('feature_count', '-')
        exported = f"{r.get('states_exported', '-')}/{r.get('states_total', '-')}" if r['status'] == 'success' else r.get('filter_reason', r.get('error', '-'))[:30]
        t = r.get('time_seconds', '-')
        size = r.get('total_size_kb', '-')
        lines.append(f"| {r['data_id']} | {status} | {features} | {exported} | {t} | {size} |")
    
    lines.extend([
        "",
        "## Full Run Estimates (178k models)",
        "",
    ])
    
    if summary.get('avg_time_success'):
        rate = summary['success_rate']
        avg_t = summary['avg_time_success']
        est_hours = (avg_t * 178000) / 3600
        lines.extend([
            f"- Success rate: {rate:.0f}%",
            f"- Estimated processable models: {int(178000 * rate / 100)}",
            f"- Sequential time: ~{est_hours:.0f} hours ({est_hours/24:.0f} days)",
            f"- 10 parallel workers: ~{est_hours/10:.0f} hours ({est_hours/10/24:.1f} days)",
            f"- 50 parallel workers: ~{est_hours/50:.0f} hours ({est_hours/50/24:.1f} days)",
        ])
    
    return "\n".join(lines) + "\n"


if __name__ == '__main__':
    run_batch()
