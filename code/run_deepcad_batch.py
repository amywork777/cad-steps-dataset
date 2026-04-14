#!/usr/bin/env python3
"""
Run the CAD-Steps export pipeline on DeepCAD-verified models.

These models are from the DeepCAD test set, which means they were
already verified to contain only sketch+extrude operations.
This should give us a much higher success rate than random ABC models.
"""

import os
import json
import time
import traceback

from onshape_api.client import Client
from export_steps import export_all_states, parse_onshape_url, get_feature_list

# DeepCAD test set models (from objects_0000.yml, verified sketch+extrude)
DEEPCAD_MODELS = {
    '00009051': 'https://cad.onshape.com/documents/4b3b521f6e6c409ab75438fc/w/7c6fbf90fa5e40e4a6dbbdd6/e/9e38511fb4eb40fa96ce36ce',
    '00008841': 'https://cad.onshape.com/documents/63a9b48ded484effbd6339a1/w/c3986cc163b140d8aebd02a2/e/62b2d0cdacfe4143a6d288b7',
    '00004596': 'https://cad.onshape.com/documents/976c446b3cc344ac89fb8425/w/2c2ca46622fd453e89578fc2/e/83b34e578b8d4f448dd410c2',
    '00005807': 'https://cad.onshape.com/documents/157148e03e934eb58a2a45ee/w/1797ef10c145460bba7b4d31/e/8f9c7589eef0417e93181333',
    '00006481': 'https://cad.onshape.com/documents/b31420b40eae4693afee638f/w/7abd4c02d0bb418696a74fec/e/c2303a937974457ca4f2ca97',
    '00006221': 'https://cad.onshape.com/documents/4eaf4323c5af4d758a782423/w/92741c85986342dfb1c5f3e3/e/c9fb57148fad47bc8e42518e',
    '00009834': 'https://cad.onshape.com/documents/bba73493c25a414eae596fe1/w/4f3af2e761864463835aaeb3/e/c971c9af65544d3aaee5ba9f',
    '00007551': 'https://cad.onshape.com/documents/39b8753e288548acb61c7b2a/w/a2e8116ef0424176bd3d6633/e/a46897cd200f4abdab72af63',
    '00006345': 'https://cad.onshape.com/documents/495c9a76b2e542548ea1c52c/w/bf455530c62a4257ada64f1e/e/e67ed7392cd96bcc439a9047',
    '00008597': 'https://cad.onshape.com/documents/2af3c80265da46e7aa5a7153/w/4590367c874544d4ab258288/e/91f66109c6048852e8dba3ab',
    '00007648': 'https://cad.onshape.com/documents/34b1460a56ff4f2cace1265d/w/9c960f04195241e8bbe518dc/e/d4b3365dafd64d2aa059bd03',
    '00005545': 'https://cad.onshape.com/documents/6a94fbfec8d64c2ba6017575/w/dc0b107ac7d1445785c1b410/e/84edf33e575a4e888ba26044',
    '00007269': 'https://cad.onshape.com/documents/adfc323e64d54b67a5c4aca6/w/c9efe3ea5830429fb8b9e826/e/00e3742305f64910bbcb0d36',
    '00002718': 'https://cad.onshape.com/documents/98d8f78b1bb5495f9a193852/w/06e152e8202e4135be32fbff/e/60b599795e564308a948261c',
    '00006584': 'https://cad.onshape.com/documents/b3d0eb0739bc4f9ebfdff16c/w/6d5556d09c6f4805ab437f5f/e/c5f08fbe42b74a9a9f13a124',
}


def run_batch():
    output_base = os.path.join(os.path.dirname(__file__), '..', 'data', 'deepcad_batch')
    os.makedirs(output_base, exist_ok=True)

    client = Client(creds='./creds.json', logging=False)

    results = []
    total_start = time.time()

    print("=" * 70)
    print("CAD-Steps - DeepCAD Verified Models Batch")
    print(f"Models: {len(DEEPCAD_MODELS)}")
    print("=" * 70)

    for i, (data_id, url) in enumerate(DEEPCAD_MODELS.items()):
        print(f"\n[{i+1}/{len(DEEPCAD_MODELS)}] Model {data_id}")

        model_start = time.time()
        result = {'data_id': data_id, 'url': url, 'status': 'unknown'}

        # Quick feature check
        try:
            did, wid, eid = parse_onshape_url(url)
            features = get_feature_list(client, did, wid, eid)
            
            if not features:
                result['status'] = 'no_features'
                result['time_seconds'] = round(time.time() - model_start, 1)
                results.append(result)
                print(f"  ✗ No features")
                continue

            feature_types = [f['featureType'] for f in features]
            print(f"  Features: {len(features)} ({', '.join(set(feature_types))})")
            result['feature_count'] = len(features)
            result['feature_types'] = list(set(feature_types))

        except Exception as e:
            result['status'] = 'api_error'
            result['error'] = str(e)[:200]
            result['time_seconds'] = round(time.time() - model_start, 1)
            results.append(result)
            print(f"  ✗ API error: {e}")
            continue

        # Run full export
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
                exported = sum(1 for s in metadata.get('states', []) if s.get('exported'))
                total_states = len(metadata.get('states', []))
                step_files = [f for f in os.listdir(model_dir) if f.endswith('.step')]
                total_size = sum(os.path.getsize(os.path.join(model_dir, f)) for f in step_files)

                result['status'] = 'success'
                result['states_exported'] = exported
                result['states_total'] = total_states
                result['step_files'] = len(step_files)
                result['total_size_kb'] = round(total_size / 1024, 1)

                print(f"  ✓ {exported}/{total_states} states, {len(step_files)} files, {result['total_size_kb']:.1f} KB")

        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)[:200]
            print(f"  ✗ Error: {e}")

        result['time_seconds'] = round(time.time() - model_start, 1)
        print(f"  Time: {result['time_seconds']}s")
        results.append(result)
        time.sleep(2)

    total_time = round(time.time() - total_start, 1)

    # Summary
    succeeded = [r for r in results if r['status'] == 'success']
    api_errors = [r for r in results if r['status'] == 'api_error']
    export_failed = [r for r in results if r['status'] == 'export_failed']
    errors = [r for r in results if r['status'] == 'error']

    summary = {
        'total': len(results),
        'succeeded': len(succeeded),
        'api_errors': len(api_errors),
        'export_failed': len(export_failed),
        'errors': len(errors),
        'total_time': total_time,
        'success_rate': round(len(succeeded) / len(results) * 100, 1) if results else 0,
    }

    if succeeded:
        times = [r['time_seconds'] for r in succeeded]
        summary['avg_time'] = round(sum(times) / len(times), 1)
        summary['total_step_files'] = sum(r.get('step_files', 0) for r in succeeded)
        summary['total_size_kb'] = round(sum(r.get('total_size_kb', 0) for r in succeeded), 1)
        summary['total_states'] = sum(r.get('states_exported', 0) for r in succeeded)

    # Save
    with open(os.path.join(output_base, 'results.json'), 'w') as f:
        json.dump({'results': results, 'summary': summary}, f, indent=2)

    print(f"\n{'=' * 70}")
    print("BATCH COMPLETE")
    print(f"{'=' * 70}")
    print(f"Total time: {total_time}s ({total_time/60:.1f} min)")
    print(f"Success: {summary['succeeded']}/{summary['total']} ({summary['success_rate']}%)")
    print(f"API errors (404/deleted): {summary['api_errors']}")
    print(f"Export failures: {summary['export_failed']}")
    print(f"Other errors: {summary['errors']}")

    if succeeded:
        print(f"\nAvg time/model: {summary['avg_time']}s")
        print(f"Total STEP files: {summary['total_step_files']}")
        print(f"Total output: {summary['total_size_kb']} KB")
        
        # Adjusted estimate: only count models we can reach (exclude 404s)
        reachable = len(succeeded) + len(export_failed) + len(errors)
        reachable_rate = len(succeeded) / reachable * 100 if reachable else 0
        api_error_rate = len(api_errors) / len(results) * 100
        
        print(f"\n--- Full Run Projections ---")
        print(f"API error rate (deleted docs): {api_error_rate:.0f}%")
        print(f"Success rate (reachable models): {reachable_rate:.0f}%")
        est_reachable = int(178000 * (1 - api_error_rate/100))
        est_success = int(est_reachable * reachable_rate / 100)
        est_hours = (summary['avg_time'] * 178000) / 3600
        print(f"Estimated reachable: {est_reachable}")
        print(f"Estimated successful: {est_success}")
        print(f"Sequential: ~{est_hours:.0f} hours ({est_hours/24:.0f} days)")
        print(f"10 parallel: ~{est_hours/10:.0f} hours ({est_hours/10/24:.1f} days)")


if __name__ == '__main__':
    run_batch()
