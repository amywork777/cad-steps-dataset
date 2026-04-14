#!/usr/bin/env python3
"""
Test the Onshape API connection and verify credentials work.

Usage:
    python test_connection.py
"""

import json
import sys
from onshape_api.client import Client


def test_basic_connection(client):
    """Test 1: List documents to verify API authentication works."""
    print("Test 1: Listing documents...")
    try:
        res = client.list_documents()
        if res.status_code == 200:
            docs = res.json()
            doc_count = len(docs.get('items', []))
            print(f"  ✓ Connected! Found {doc_count} documents in account.")
            if doc_count > 0:
                for doc in docs['items'][:3]:
                    print(f"    - {doc.get('name', 'unnamed')} (id: {doc['id'][:12]}...)")
            return True
        else:
            print(f"  ✗ Failed with status {res.status_code}")
            print(f"    Response: {res.text[:200]}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_public_document(client):
    """Test 2: Access a public DeepCAD example document."""
    print("\nTest 2: Accessing public DeepCAD example document...")
    # This is one of the test examples from the original onshape-cad-parser
    link = 'https://cad.onshape.com/documents/4185972a944744d8a7a0f2b4/w/d82d7eef8edf4342b7e49732/e/b6d6b562e8b64e7ea50d8325'
    parts = link.split("/")
    did, wid, eid = parts[-5], parts[-3], parts[-1]

    try:
        res = client.get_features(did, wid, eid)
        if res.status_code == 200:
            data = res.json()
            features = data.get('features', [])
            print(f"  ✓ Got feature list! {len(features)} features found.")
            for feat in features:
                msg = feat.get('message', {})
                feat_type = msg.get('featureType', 'unknown')
                feat_name = msg.get('name', 'unnamed')
                feat_id = msg.get('featureId', '?')
                print(f"    - [{feat_type}] {feat_name} (id: {feat_id})")
            return True
        else:
            print(f"  ✗ Failed with status {res.status_code}")
            print(f"    Response: {res.text[:200]}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_rollback_api(client):
    """Test 3: Verify that the rollback API endpoint is accessible."""
    print("\nTest 3: Testing rollback API availability...")
    # Use the same public document
    link = 'https://cad.onshape.com/documents/4185972a944744d8a7a0f2b4/w/d82d7eef8edf4342b7e49732/e/b6d6b562e8b64e7ea50d8325'
    parts = link.split("/")
    did, wid, eid = parts[-5], parts[-3], parts[-1]

    try:
        # Try to get parts at the current state
        res = client.get_parts(did, wid, eid)
        if res.status_code == 200:
            parts_data = res.json()
            print(f"  ✓ Parts API works! {len(parts_data)} parts found.")
            for part in parts_data:
                print(f"    - {part.get('name', 'unnamed')} (partId: {part.get('partId', '?')[:12]}...)")
            return True
        else:
            print(f"  ✗ Parts API returned status {res.status_code}")
            print(f"    (This might be expected for public docs without write access)")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_step_export_api(client):
    """Test 4: Check if STEP translation API is accessible."""
    print("\nTest 4: Testing STEP export API...")
    link = 'https://cad.onshape.com/documents/4185972a944744d8a7a0f2b4/w/d82d7eef8edf4342b7e49732/e/b6d6b562e8b64e7ea50d8325'
    parts = link.split("/")
    did, wid, eid = parts[-5], parts[-3], parts[-1]

    try:
        result = client.export_step(did, wid, eid)
        if result is not None:
            print(f"  ✓ STEP translation request submitted!")
            print(f"    Translation ID: {result.get('id', 'unknown')}")
            print(f"    Status: {result.get('requestState', 'unknown')}")
            return True
        else:
            print(f"  ✗ No parts found or translation failed")
            print(f"    (This is expected for public docs you don't own)")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def main():
    print("=" * 60)
    print("Onshape API Connection Test")
    print("=" * 60)

    # Load and verify credentials file
    try:
        with open('creds.json') as f:
            creds = json.load(f)
        stack = list(creds.keys())[0]
        ak = creds[stack]['access_key']
        print(f"Credentials loaded: stack={stack}, key={ak[:8]}...")
    except Exception as e:
        print(f"Failed to load creds.json: {e}")
        sys.exit(1)

    client = Client(creds='./creds.json', logging=False)

    results = []
    results.append(("Basic Connection", test_basic_connection(client)))
    results.append(("Public Document", test_public_document(client)))
    results.append(("Parts API", test_rollback_api(client)))
    results.append(("STEP Export", test_step_export_api(client)))

    print("\n" + "=" * 60)
    print("Summary:")
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
    print("=" * 60)

    passed = sum(1 for _, p in results if p)
    total = len(results)
    print(f"\n{passed}/{total} tests passed")

    if passed == 0:
        print("\nAll tests failed. Check your API credentials in creds.json")
        sys.exit(1)


if __name__ == '__main__':
    main()
