#!/usr/bin/env python3
"""
Export STEP geometry at each rollback state of a CAD model.

This is the core new functionality for the CAD-Steps dataset.
For each model, it:
1. Gets the feature list
2. Iterates through features, rolling back to each state
3. Exports STEP geometry at each state
4. Saves pairs: (geometry_N.step, operation_N+1, geometry_N+1.step)

Usage:
    python export_steps.py --url <onshape_url> --output_dir <dir>
    python export_steps.py --test
"""

import os
import json
import time
import argparse
from onshape_api.client import Client


def parse_onshape_url(url):
    """Extract document, workspace, and element IDs from an Onshape URL."""
    parts = url.rstrip('/').split('/')
    # URL format: .../documents/{did}/w/{wid}/e/{eid}
    did = parts[parts.index('documents') + 1]
    wid = parts[parts.index('w') + 1]
    eid = parts[parts.index('e') + 1]
    return did, wid, eid


def get_feature_list(client, did, wid, eid):
    """Get the ordered list of features in a part studio."""
    res = client.get_features(did, wid, eid)
    if res.status_code != 200:
        raise Exception(f"Failed to get features: {res.status_code} {res.text[:200]}")
    data = res.json()
    features = []
    for feat in data.get('features', []):
        msg = feat.get('message', {})
        features.append({
            'featureId': msg.get('featureId'),
            'featureType': msg.get('featureType'),
            'name': msg.get('name'),
        })
    return features


def wait_for_translation(client, translation_id, timeout=120, poll_interval=3):
    """Poll translation status until complete or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        res = client.get_translation_status(translation_id)
        if res.status_code != 200:
            raise Exception(f"Translation status check failed: {res.status_code}")
        status = res.json()
        state = status.get('requestState', '')
        if state == 'DONE':
            return status
        elif state == 'FAILED':
            raise Exception(f"Translation failed: {status.get('failureReason', 'unknown')}")
        time.sleep(poll_interval)
    raise TimeoutError(f"Translation timed out after {timeout}s")


def export_step_at_state(client, did, wid, eid, output_path):
    """
    Export STEP file at the current rollback state.

    Note: The rollback bar must be set BEFORE calling this.
    This initiates a translation, waits for completion, and downloads the result.
    """
    # Check if there are any parts at current state
    parts_res = client.get_parts(did, wid, eid)
    if parts_res.status_code != 200 or not parts_res.json():
        print(f"    No parts at current state, skipping STEP export")
        return False

    # Request STEP translation
    translation = client.export_step(did, wid, eid)
    if translation is None:
        print(f"    Translation request failed")
        return False

    trans_id = translation.get('id')
    print(f"    Translation {trans_id} submitted, waiting...")

    # Wait for completion
    try:
        result = wait_for_translation(client, trans_id)
    except (TimeoutError, Exception) as e:
        print(f"    Translation error: {e}")
        return False

    # Download the result
    result_id = result.get('resultExternalDataIds', [None])[0]
    if not result_id:
        print(f"    No result document ID found")
        return False

    download = client.download_translated_document(did, result_id)
    if download.status_code != 200:
        print(f"    Download failed: {download.status_code}")
        return False

    with open(output_path, 'wb') as f:
        f.write(download.content)
    print(f"    ✓ Saved: {output_path} ({len(download.content)} bytes)")
    return True


def export_all_states(client, url, output_dir, skip_sketches=True):
    """
    Export STEP files at every rollback state of a model.

    Args:
        client: Onshape API client
        url: Onshape document URL
        output_dir: Directory to save STEP files and metadata
        skip_sketches: If True, only export after extrude ops (sketch-only
                       states have no 3D geometry worth exporting)
    """
    did, wid, eid = parse_onshape_url(url)
    os.makedirs(output_dir, exist_ok=True)

    print(f"Document: {did}")
    print(f"Workspace: {wid}")
    print(f"Element: {eid}")

    # Get feature list
    features = get_feature_list(client, did, wid, eid)
    print(f"\nFound {len(features)} features:")
    for i, feat in enumerate(features):
        print(f"  [{i}] {feat['featureType']}: {feat['name']} (id: {feat['featureId']})")

    # Save feature metadata
    metadata = {
        'url': url,
        'did': did,
        'wid': wid,
        'eid': eid,
        'features': features,
        'states': []
    }

    # Export STEP at each state
    exported_count = 0
    for i in range(len(features)):
        feat = features[i]
        print(f"\nState {i}: after '{feat['name']}' ({feat['featureType']})")

        # Skip sketch-only states if requested
        if skip_sketches and feat['featureType'] == 'newSketch':
            print(f"  Skipping (sketch-only state)")
            metadata['states'].append({
                'index': i,
                'feature': feat,
                'exported': False,
                'reason': 'sketch-only'
            })
            continue

        # Set rollback bar to include features up to index i
        # rollbackIndex = i+1 means "after the i-th feature"
        print(f"  Setting rollback to index {i + 1}...")
        rollback_res = client.set_rollback_bar(did, wid, eid, index=i + 1)

        if rollback_res.status_code not in (200, 201):
            print(f"  ✗ Rollback failed: {rollback_res.status_code}")
            print(f"    {rollback_res.text[:200]}")
            metadata['states'].append({
                'index': i,
                'feature': feat,
                'exported': False,
                'reason': f'rollback_failed_{rollback_res.status_code}'
            })
            continue

        # Small delay to let Onshape process
        time.sleep(1)

        # Export STEP
        step_path = os.path.join(output_dir, f"state_{i:04d}.step")
        success = export_step_at_state(client, did, wid, eid, step_path)

        metadata['states'].append({
            'index': i,
            'feature': feat,
            'exported': success,
            'step_file': f"state_{i:04d}.step" if success else None
        })

        if success:
            exported_count += 1

    # Reset rollback to end
    print(f"\nResetting rollback bar to end...")
    client.set_rollback_bar(did, wid, eid, index=-1)

    # Save metadata
    meta_path = os.path.join(output_dir, 'metadata.json')
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"\n✓ Done! Exported {exported_count}/{len(features)} states")
    print(f"  Metadata: {meta_path}")

    return metadata


def main():
    arg_parser = argparse.ArgumentParser(description="Export STEP at each CAD construction state")
    arg_parser.add_argument("--url", type=str, help="Onshape document URL")
    arg_parser.add_argument("--output_dir", type=str, default="./step_output",
                            help="Output directory")
    arg_parser.add_argument("--test", action="store_true",
                            help="Run on test example")
    arg_parser.add_argument("--creds", type=str, default="./creds.json",
                            help="Path to credentials file")
    arg_parser.add_argument("--include-sketches", action="store_true",
                            help="Also export states after sketch-only features")
    args = arg_parser.parse_args()

    client = Client(creds=args.creds, logging=False)

    if args.test:
        test_url = 'https://cad.onshape.com/documents/4185972a944744d8a7a0f2b4/w/d82d7eef8edf4342b7e49732/e/b6d6b562e8b64e7ea50d8325'
        print("Running test export on DeepCAD example...")
        print(f"URL: {test_url}\n")
        export_all_states(
            client, test_url,
            output_dir='./step_output_test',
            skip_sketches=not args.include_sketches
        )
    elif args.url:
        export_all_states(
            client, args.url,
            output_dir=args.output_dir,
            skip_sketches=not args.include_sketches
        )
    else:
        arg_parser.print_help()


if __name__ == '__main__':
    main()
