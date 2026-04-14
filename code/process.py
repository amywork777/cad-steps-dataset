"""
Main processing script for CAD-Steps dataset.
Python 3 port of onshape-cad-parser/process.py

Usage:
    python process.py --test          # Run on test examples
    python process.py --link_data_folder /path/to/links  # Process ABC dataset links
"""

import os
import json
import argparse

import yaml
import numpy as np
from tqdm import tqdm
from joblib import delayed, Parallel

from parser import FeatureListParser
from onshape_api.client import Client

# Create Onshape client
c = Client(creds='./creds.json', logging=False)


def process_one(data_id, link, save_dir):
    save_path = os.path.join(save_dir, f"{data_id}.json")

    v_list = link.split("/")
    did, wid, eid = v_list[-5], v_list[-3], v_list[-1]

    # Filter data that uses operations other than sketch + extrude
    try:
        ofs_data = c.get_features(did, wid, eid).json()
        for item in ofs_data['features']:
            if item['message']['featureType'] not in ['newSketch', 'extrude']:
                return 0
    except Exception as e:
        print(f"[{data_id}] contain unsupported features: {e}")
        return 0

    # Parse detailed CAD operations
    try:
        feature_parser = FeatureListParser(c, did, wid, eid, data_id=data_id)
        result = feature_parser.parse()
    except Exception as e:
        print(f"[{data_id}] feature parsing fails: {e}")
        return 0

    if len(result["sequence"]) < 2:
        return 0

    with open(save_path, 'w') as fp:
        json.dump(result, fp, indent=1)
    return len(result["sequence"])


def main():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--test", action="store_true", help="Test with some examples")
    arg_parser.add_argument("--link_data_folder", default=None, type=str,
                            help="Data folder of Onshape links from ABC dataset")
    args = arg_parser.parse_args()

    if args.test:
        data_examples = {
            '00000352': 'https://cad.onshape.com/documents/4185972a944744d8a7a0f2b4/w/d82d7eef8edf4342b7e49732/e/b6d6b562e8b64e7ea50d8325',
            '00001272': 'https://cad.onshape.com/documents/b53ece83d8964b44bbf1f8ed/w/6b2f1aad3c43402c82009c85/e/91cb13b68f164c2eba845ce6',
            '00001616': 'https://cad.onshape.com/documents/8c3b97c1382c43bab3eb1b48/w/43439c4e192347ecbf818421/e/63b575e3ac654545b571eee6',
        }
        save_dir = "examples"
        os.makedirs(save_dir, exist_ok=True)
        for data_id, link in data_examples.items():
            print(f"Processing: {data_id}")
            result = process_one(data_id, link, save_dir)
            print(f"  -> {result} features parsed")
    else:
        if not args.link_data_folder:
            print("Please specify --link_data_folder or use --test")
            return

        dwe_dir = args.link_data_folder
        data_root = os.path.dirname(dwe_dir)
        filenames = sorted(os.listdir(dwe_dir))

        for name in filenames:
            truck_id = name.split('.')[0].split('_')[-1]
            print(f"Processing truck: {truck_id}")

            save_dir = os.path.join(data_root, f"processed/{truck_id}")
            os.makedirs(save_dir, exist_ok=True)

            dwe_path = os.path.join(dwe_dir, name)
            with open(dwe_path, 'r') as fp:
                dwe_data = yaml.safe_load(fp)

            total_n = len(dwe_data)
            count = Parallel(n_jobs=10, verbose=2)(
                delayed(process_one)(data_id, link, save_dir)
                for data_id, link in dwe_data.items()
            )
            count = np.array(count)
            print(f"valid: {np.sum(count > 0)}\ntotal: {total_n}")
            print("distribution:")
            for n in np.unique(count):
                print(n, np.sum(count == n))


if __name__ == '__main__':
    main()
