#!/usr/bin/env python3
"""
Export STEP geometry at each rollback state of a CAD model.

This is the core new functionality for the CAD-Steps dataset.

WORKFLOW:
1. Copy the source document (required for write access to rollback bar)
2. Get the feature list from the part studio
3. For each feature, set the rollback bar and export STEP geometry
4. Clean up the copy when done

For each model, the output is:
    state_0000.step  (geometry after feature 0)
    state_0001.step  (geometry after feature 1)
    ...
    metadata.json    (feature list + mapping)

Usage:
    python3 export_steps.py --url <onshape_url> --output_dir <dir>
    python3 export_steps.py --test
"""

import os
import json
import time
import argparse
from onshape_api.client import Client


def parse_onshape_url(url):
    """Extract document, workspace, and element IDs from an Onshape URL."""
    parts = url.rstrip('/').split('/')
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


def find_matching_element(client, did, wid, original_eid, original_elements=None):
    """
    Find the element in a copied document that corresponds to the original element.

    Matches by name and type since element IDs change when copying.
    """
    # Get elements from both docs
    if original_elements is None:
        return None

    # Find the original element's name and type
    original_elem = None
    for elem in original_elements:
        if elem['id'] == original_eid:
            original_elem = elem
            break

    if not original_elem:
        return None

    # Find matching element in copy
    copy_elem_res = client.get_elements(did, wid)
    if copy_elem_res.status_code != 200:
        return None

    for elem in copy_elem_res.json():
        if (elem.get('name') == original_elem.get('name') and
                elem.get('type') == original_elem.get('type')):
            return elem['id']

    return None


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
    The rollback bar must be set BEFORE calling this.
    """
    # Request STEP translation (respects rollback bar)
    translation = client.export_step(did, wid, eid)
    if translation is None:
        print(f"    No parts at current state or translation failed")
        return False

    trans_id = translation.get('id')
    print(f"    Translation {trans_id[:12]}... submitted, waiting...")

    try:
        result = wait_for_translation(client, trans_id)
    except (TimeoutError, Exception) as e:
        print(f"    Translation error: {e}")
        return False

    # Download the result
    result_ids = result.get('resultExternalDataIds', [])
    if not result_ids:
        print(f"    No result document ID found")
        return False

    result_id = result_ids[0]
    download = client.download_translated_document(did, result_id)
    if download.status_code != 200:
        print(f"    Download failed: {download.status_code}")
        return False

    with open(output_path, 'wb') as f:
        f.write(download.content)
    size_kb = len(download.content) / 1024
    print(f"    ✓ Saved: {output_path} ({size_kb:.1f} KB)")
    return True


def export_all_states(client, url, output_dir, skip_sketches=True, cleanup=True, quiet=False):
    """
    Export STEP files at every rollback state of a model.

    Pipeline:
    1. Read features from original document
    2. Copy document (needed for rollback write access)
    3. For each feature state, rollback and export STEP
    4. Clean up copy

    Args:
        client: Onshape API client
        url: Onshape document URL
        output_dir: Directory to save STEP files and metadata
        skip_sketches: If True, only export after extrude ops
        cleanup: If True, delete the copied document when done
        quiet: If True, suppress most print output
    """
    def log(msg):
        if not quiet:
            print(msg)
    did, wid, eid = parse_onshape_url(url)
    os.makedirs(output_dir, exist_ok=True)

    print(f"Source document: {did}")
    print(f"Source workspace: {wid}")
    print(f"Source element: {eid}")

    # Step 1: Get features and elements from source
    features = get_feature_list(client, did, wid, eid)
    print(f"\nFound {len(features)} features:")
    for i, feat in enumerate(features):
        print(f"  [{i}] {feat['featureType']}: {feat['name']} (id: {feat['featureId']})")

    if not features:
        print("No features found, nothing to export.")
        return None

    # Get source elements for matching
    source_elem_res = client.get_elements(did, wid)
    source_elements = source_elem_res.json() if source_elem_res.status_code == 200 else []

    # Step 2: Copy the document
    print(f"\nCopying document for rollback access...")
    copy_result = client.copy_document(did, wid, name=f"CAD-Steps_{did[:8]}")
    if not copy_result:
        print("✗ Failed to copy document. Cannot proceed with rollback.")
        print("  (Rollback requires write access; public docs must be copied first)")
        return None

    copy_did = copy_result['newDocumentId']
    copy_wid = copy_result['newWorkspaceId']
    print(f"  ✓ Copied to: {copy_did} / {copy_wid}")

    # Wait for copy to settle
    time.sleep(3)

    # Step 3: Find matching element in copy
    copy_eid = find_matching_element(client, copy_did, copy_wid, eid, source_elements)
    if not copy_eid:
        # If matching fails, try finding any part studio with features
        print("  Could not match element by name, searching for part studio with features...")
        copy_elem_res = client.get_elements(copy_did, copy_wid)
        for elem in copy_elem_res.json():
            if elem.get('type') == 'Part Studio':
                feat_res = client.get_features(copy_did, copy_wid, elem['id'])
                if feat_res.json().get('features', []):
                    copy_eid = elem['id']
                    print(f"  Found: {elem.get('name')} (id: {copy_eid})")
                    break

    if not copy_eid:
        print("  ✗ Could not find matching part studio in copy")
        if cleanup:
            client.delete_document(copy_did)
        return None

    # Verify features match
    copy_features = get_feature_list(client, copy_did, copy_wid, copy_eid)
    print(f"  Copy has {len(copy_features)} features (source had {len(features)})")

    # Save metadata
    metadata = {
        'source_url': url,
        'source_did': did,
        'source_wid': wid,
        'source_eid': eid,
        'copy_did': copy_did,
        'copy_wid': copy_wid,
        'copy_eid': copy_eid,
        'features': copy_features,
        'states': []
    }

    # Step 4: Export STEP at each state
    exported_count = 0
    use_features = copy_features if copy_features else features

    for i in range(len(use_features)):
        feat = use_features[i]
        print(f"\nState {i}: after '{feat['name']}' ({feat['featureType']})")

        if skip_sketches and feat['featureType'] == 'newSketch':
            print(f"  Skipping (sketch-only state)")
            metadata['states'].append({
                'index': i,
                'feature': feat,
                'exported': False,
                'reason': 'sketch-only'
            })
            continue

        # Set rollback bar
        rollback_idx = i + 1  # rollbackIndex N means "after feature N-1"
        print(f"  Setting rollback to index {rollback_idx}...")
        rb_res = client.set_rollback_bar(copy_did, copy_wid, copy_eid, index=rollback_idx)

        if rb_res.status_code != 200:
            print(f"  ✗ Rollback failed: {rb_res.status_code}")
            metadata['states'].append({
                'index': i,
                'feature': feat,
                'exported': False,
                'reason': f'rollback_failed_{rb_res.status_code}'
            })
            continue

        time.sleep(1)

        # Export STEP
        step_path = os.path.join(output_dir, f"state_{i:04d}.step")
        success = export_step_at_state(client, copy_did, copy_wid, copy_eid, step_path)

        metadata['states'].append({
            'index': i,
            'feature': feat,
            'exported': success,
            'step_file': f"state_{i:04d}.step" if success else None
        })

        if success:
            exported_count += 1

    # Step 5: Reset rollback and optionally clean up
    print(f"\nResetting rollback bar...")
    client.set_rollback_bar(copy_did, copy_wid, copy_eid, index=-1)

    if cleanup:
        print(f"Cleaning up copy...")
        client.delete_document(copy_did)
        print(f"  ✓ Deleted copy: {copy_did}")

    # Save metadata
    meta_path = os.path.join(output_dir, 'metadata.json')
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"\n{'='*50}")
    print(f"✓ Done! Exported {exported_count}/{len(use_features)} states")
    print(f"  Output: {output_dir}")
    print(f"  Metadata: {meta_path}")

    return metadata


def main():
    arg_parser = argparse.ArgumentParser(
        description="Export STEP geometry at each CAD construction state"
    )
    arg_parser.add_argument("--url", type=str, help="Onshape document URL")
    arg_parser.add_argument("--output_dir", type=str, default="./step_output",
                            help="Output directory")
    arg_parser.add_argument("--test", action="store_true",
                            help="Run on test example")
    arg_parser.add_argument("--creds", type=str, default="./creds.json",
                            help="Path to credentials file")
    arg_parser.add_argument("--include-sketches", action="store_true",
                            help="Also export states after sketch-only features")
    arg_parser.add_argument("--no-cleanup", action="store_true",
                            help="Don't delete the copied document after export")
    args = arg_parser.parse_args()

    client = Client(creds=args.creds, logging=False)

    if args.test:
        # Use one of the DeepCAD test examples
        test_url = 'https://cad.onshape.com/documents/4185972a944744d8a7a0f2b4/w/d82d7eef8edf4342b7e49732/e/b6d6b562e8b64e7ea50d8325'
        print("Running test export on DeepCAD example (6-Axis Robot Arm - Electronics)...")
        print(f"URL: {test_url}\n")
        export_all_states(
            client, test_url,
            output_dir='./step_output_test',
            skip_sketches=not args.include_sketches,
            cleanup=not args.no_cleanup
        )
    elif args.url:
        export_all_states(
            client, args.url,
            output_dir=args.output_dir,
            skip_sketches=not args.include_sketches,
            cleanup=not args.no_cleanup
        )
    else:
        arg_parser.print_help()


if __name__ == '__main__':
    main()
