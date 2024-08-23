import os
import json
import msgpack
import jmespath
from collections import defaultdict
from typing import Dict, List
from equi7grid.equi7grid import Equi7Grid
from tools_shared_variables import MAGNITUDE_DICT

def load_eval_cat(path: str) -> Dict:
    with open(path, 'r') as f:
        return json.load(f)

def load_flat_bench(path: str) -> Dict:
    with open(path, 'rb') as f:
        return msgpack.load(f)

def defaultdict_to_dict(d):
    if isinstance(d, defaultdict):
        d = {k: defaultdict_to_dict(v) for k, v in d.items()}
    return d

def extract_lid_from_asset(href: str) -> str:
    parts = href.split('/')
    for part in parts:
        if part.startswith('ahps_'):
            return part.split('_')[1]
    return 'default'

def extract_magnitude_from_asset(href: str) -> str:
    magnitude_keywords = ['action', 'minor', 'moderate', 'major', '100yr', '500yr']
    for keyword in magnitude_keywords:
        if keyword in href.lower():
            return keyword
    return 'default'


def extract_huc(properties: Dict) -> str:
    huc_keys = [key for key in properties.keys() if 'huc' in key.lower()]
    for huc_key in huc_keys:
        huc_value = properties[huc_key]
        if huc_value:
            return str(huc_value)
    return None

def process_item(item: Dict, benchmark_category: str, result: Dict):
    properties = item.get('properties', {})
    assets = item.get('assets', {})    
    huc = extract_huc(properties)
    if not huc:
        return
    for asset_key, asset_value in assets.items():
        asset_key_lower = asset_key.lower()
        href = asset_value.get('href', '')
        magnitude = extract_magnitude_from_asset(href)
        
        if benchmark_category == 'ble':
            if 'extent' in asset_key_lower:
                result[huc][benchmark_category][magnitude]['extents'].append(href)
            elif 'flow' in asset_key_lower:
                result[huc][benchmark_category][magnitude]['flowfiles'].append(href)
        else:
            lid = extract_lid_from_asset(href)
            if 'extent' in asset_key_lower:
                result[huc][benchmark_category][magnitude][lid]['extents'].append(href)
            elif 'flow' in asset_key_lower:
                result[huc][benchmark_category][magnitude][lid]['flowfiles'].append(href)

def get_eval_catalog_data(eval_catalog: Dict) -> Dict[str, Dict[str, Dict[str, List[str]]]]:
    temp_result = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    
    for key, value in eval_catalog.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            for item in value:
                if 'huc' in item and item['huc'] is not None and 'data_version' in item:
                    version = item['data_version']
                    huc = item['huc']
                    filepath = os.path.join(item.get('dir_path', ''), item.get('filename', ''))
                    temp_result[version][huc][key].append(filepath)
    
    return defaultdict_to_dict(temp_result)

def get_stac_catalog_data(stac_catalog: Dict, benchmark_categories: List[str]) -> Dict[str, Dict[str, Dict[str, Dict[str, List[str]]]]]:
    def lid_dict():
        return {"flowfiles": [], "extents": []}
    
    def ble_dict():
        return defaultdict(lambda: {"flowfiles": [], "extents": []})
    
    result = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(lid_dict))))
    
    for benchmark_category in benchmark_categories:
        if benchmark_category == 'ble':
            result = defaultdict(lambda: defaultdict(ble_dict))
        
        query = f'links[?id && contains(id, `{benchmark_category}`)].[id, items[]]'
        collections = jmespath.search(query, stac_catalog)
        for collection_id, items in collections:
            for item in items:
                process_item(item, benchmark_category, result)
    
    return defaultdict_to_dict(result)

def get_eval_data(eval_catalog: Dict, stac_catalog: Dict, benchmark_categories: List[str]) -> Dict[str, Dict[str, Dict[str, Dict[str, List[str]]]]]:
    if "all" in benchmark_categories:
        benchmark_categories = list(MAGNITUDE_DICT.keys())

    eval_data = get_eval_catalog_data(eval_catalog)
    stac_data = get_stac_catalog_data(stac_catalog, benchmark_categories)
    
    result = defaultdict(lambda: defaultdict(dict))
    
    for version, hucs_data in eval_data.items():
        for huc, data_types in hucs_data.items():
            result[version][huc]['hand'] = data_types
    
    for huc in stac_data.keys():
        for version in result.keys():
            if huc in result[version]:
                result[version][huc].update(stac_data[huc])
    
    if not result:
        raise ValueError(f"No common data found between eval_catalog and stac_catalog for benchmark categories: {benchmark_categories}")
    
    return defaultdict_to_dict(result)
