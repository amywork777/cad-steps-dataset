#!/usr/bin/env python3
"""
Test the Onshape API connection and verify credentials work.

Tests the full pipeline:
1. API authentication
2. Reading public documents
3. Copying a document (for rollback access)
4. Rollback bar movement
5. STEP export

Usage:
    python3 test_connection.py
    python3 test_connection.py --full   # includes copy+rollback test (slower, creates temp doc)
"""

import json
import sys
import time
import argparse
from onshape_api.client import Client

# Test document: 6-Axis Robot Arm by Colin Kingsbury (public)
TEST_DOC = {
    'url': 'https://cad.onshape.com/documents/4185972a944744d8a7a0f2b4/w/d82d7eef8edf4342b7e49732/e/b6d6b562e8b64e7ea50d8325',
    'did': '4185972a944744d8a7a0f2b4',
    'wid': 'd82d7eef8edf4342b7e49732',
    'eid': 'b6d6b562e8b64e7ea50d8325',  # "Electronics" part studio
}


def test_auth(client):
    """Test 1: Verify API authentication."""
    print("Test 1: API Authentication...")
    try:
        res = client.list_documents()
        if res.status_code == 200:
            docs = res.json()
            doc_count = len(docs.get('items', []))
            print(f"  ✓ Connected! {doc_count} documents in account.")
            return True
        else:
            print(f"  ✗ Failed: status {res.status_code}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_read_features(client):
    """Test 2: Read features from a public document."""
    print("\nTest 2: Reading features from public document...")
    try:
        res = client.get_features(TEST_DOC['did'], TEST_DOC['wid'], TEST_DOC['eid'])
        if res.status_code == 200:
            features = res.json().get('features', [])
            print(f"  ✓ Got {len(features)} features")
            for feat in features[:3]:
                msg = feat.get('message', {})
                print(f"    - [{msg.get('featureType')}] {msg.get('name')}")
            if len(features) > 3:
                print(f"    ... and {len(features) - 3} more")
            return True
        else:
            print(f"  ✗ Failed: status {res.status_code}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_parts(client):
    """Test 3: Get parts list."""
    print("\nTest 3: Getting parts list...")
    try:
        res = client.get_parts(TEST_DOC['did'], TEST_DOC['wid'], TEST_DOC['eid'])
        if res.status_code == 200:
            parts = res.json()
            print(f"  ✓ Found {len(parts)} parts")
            for part in parts[:3]:
                print(f"    - {part.get('name', '?')} (id: {part.get('partId', '?')[:12]}...)")
            return True
        else:
            print(f"  ✗ Failed: status {res.status_code}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_copy_rollback_export(client):
    """Test 4 (full): Copy document, rollback, and verify STEP export."""
    print("\nTest 4: Copy + Rollback + STEP export (full pipeline)...")

    # Copy
    print("  Copying document...")
    copy = client.copy_document(TEST_DOC['did'], TEST_DOC['wid'],
                                 name='CAD-Steps API Test (auto-delete)')
    if not copy:
        print("  ✗ Copy failed")
        return False

    copy_did = copy['newDocumentId']
    copy_wid = copy['newWorkspaceId']
    print(f"  ✓ Copied: {copy_did[:12]}...")

    try:
        time.sleep(3)

        # Find matching element
        copy_elem_res = client.get_elements(copy_did, copy_wid)
        elements = copy_elem_res.json()
        ps_with_features = None
        for elem in elements:
            if elem.get('type') == 'Part Studio':
                feat_res = client.get_features(copy_did, copy_wid, elem['id'])
                feats = feat_res.json().get('features', [])
                if feats:
                    ps_with_features = (elem['id'], elem.get('name'), len(feats))
                    break

        if not ps_with_features:
            print("  ✗ No part studios with features found in copy")
            return False

        copy_eid, ps_name, feat_count = ps_with_features
        print(f"  ✓ Found '{ps_name}' with {feat_count} features")

        # Test rollback
        print("  Testing rollback...")
        for idx in [0, 2, feat_count]:
            rb = client.set_rollback_bar(copy_did, copy_wid, copy_eid, index=idx)
            if rb.status_code != 200:
                print(f"  ✗ Rollback to {idx} failed: {rb.status_code}")
                return False
        print(f"  ✓ Rollback works (tested 0, 2, {feat_count})")

        # Test STEP export at rolled-back state
        print("  Testing STEP export at rollback state 2...")
        client.set_rollback_bar(copy_did, copy_wid, copy_eid, index=2)
        time.sleep(1)
        translation = client.export_step(copy_did, copy_wid, copy_eid)
        if translation:
            trans_id = translation.get('id', '?')
            print(f"  ✓ STEP translation submitted: {trans_id[:12]}...")
        else:
            print("  ⚠ No parts at rollback state 2 (normal for sketch-only states)")

        # Reset
        client.set_rollback_bar(copy_did, copy_wid, copy_eid, index=-1)
        return True

    finally:
        # Always clean up
        print("  Cleaning up copy...")
        client.delete_document(copy_did)
        print(f"  ✓ Deleted")


def main():
    parser = argparse.ArgumentParser(description="Test Onshape API connection")
    parser.add_argument("--full", action="store_true",
                        help="Run full pipeline test (copy+rollback, slower)")
    args = parser.parse_args()

    print("=" * 55)
    print("Onshape API Connection Test for CAD-Steps Dataset")
    print("=" * 55)

    try:
        with open('creds.json') as f:
            creds = json.load(f)
        stack = list(creds.keys())[0]
        ak = creds[stack]['access_key']
        print(f"Credentials: stack={stack}, key={ak[:8]}...\n")
    except Exception as e:
        print(f"Failed to load creds.json: {e}")
        sys.exit(1)

    client = Client(creds='./creds.json', logging=False)

    results = []
    results.append(("Authentication", test_auth(client)))
    results.append(("Read Features", test_read_features(client)))
    results.append(("Parts List", test_parts(client)))

    if args.full:
        results.append(("Copy+Rollback+Export", test_copy_rollback_export(client)))

    print("\n" + "=" * 55)
    print("Results:")
    for name, passed in results:
        print(f"  {'✓' if passed else '✗'} {name}")
    print("=" * 55)

    passed = sum(1 for _, p in results if p)
    total = len(results)
    print(f"\n{passed}/{total} tests passed")

    if not args.full:
        print("\nTip: run with --full to test copy+rollback+export pipeline")


if __name__ == '__main__':
    main()
