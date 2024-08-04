import pdb
import re
import pystac
import os
import json
import boto3
from urllib.parse import urlparse

from tools_shared_variables import WORK_DIR

def download_s3_asset(asset_href, directory):
    # Parse the S3 URL
    parsed_url = urlparse(asset_href)
    bucket_name = parsed_url.netloc
    key = parsed_url.path.lstrip('/')

    # Initiate S3 connection
    s3 = boto3.client('s3')

    # Define the local file path
    local_file_path = os.path.join(directory, os.path.basename(key))

    # Download the file from S3
    s3.download_file(bucket_name, key, local_file_path)

    return local_file_path

def get_bench_asset(catalog, bench_cat, huc, lid, magnitude, asset_type):
        
    # Find the collection that contains current benchmark category in its href
    target_collection = None
    for collection in catalog.get_children():
        if bench_cat in collection.get_self_href():
            target_collection = collection
            break

    if target_collection is None:
        raise ValueError(f"No collection found with '{bench_cat}' in its href.")

    target_collection = target_collection.full_copy()
    matching_asset_href = None

    # Iterate through the items in the collection
    for item in target_collection.get_items():
        # Check if the item's properties match the provided arguments
        properties = item.properties
        huc_matches = (properties.get('ble:huc8') == int(huc) or properties.get('hec-ras:huc8') == huc)
        if lid:
            if (huc_matches and
                properties.get('hec-ras:gauge') == lid):
                # Find the matching asset in the item's assets
                for key, asset in item.assets.items():
                    if asset_type in key and str(magnitude) in key:
                        matching_asset_href = asset.href
                        break
        else:
            if (huc_matches):
                # Find the matching asset in the item's assets
                for key, asset in item.assets.items():
                    if asset_type in key and str(magnitude) in key:
                        matching_asset_href = asset.href
                        break

        if matching_asset_href:
            break

    if matching_asset_href is None:
        raise ValueError("No matching asset found.")

    # Download the matching asset and return the path
    saved_path = download_s3_asset(matching_asset_href, WORK_DIR)
    print(f"{bench_cat} {asset_type} asset at: {saved_path}")    
    return saved_path

# Example usage
# asset_path = get_bench_asset('bench_cat', 'huc_value', 'lid', 'magnitude_value', 'asset_type_value')
