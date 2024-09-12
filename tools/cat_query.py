import pdb
import os
import json
import msgpack
import pystac
from collections import defaultdict
from typing import Dict, List, Union
from osgeo import ogr
import geopandas as gpd
from shapely.geometry import Point
import pandas as pd
from equi7grid.equi7grid import Equi7Grid
from tools_shared_variables import MAGNITUDE_DICT, WORK_DIR
from tools_shared_functions import get_local_filepath

def load_eval_cat(path: str) -> Dict:
    with open(path, 'r') as f:
        return json.load(f)

def load_stac(catalog_path):
    catalog = pystac.Catalog.from_file(catalog_path)
    catalog.make_all_asset_hrefs_absolute()
    catalog.normalize_hrefs(os.path.dirname(catalog_path))
    # Fully load all collections and items
    catalog.fully_resolve()
    
    return catalog

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

# process a hec-ras item
def process_item(item: pystac.Item, benchmark_category: str, result: Dict):
    properties = item.properties
    assets = item.assets    
    huc = extract_huc(properties)
    if not huc:
        return
    for asset_key, asset_value in assets.items():
        asset_key_lower = asset_key.lower()
        href = asset_value.href
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

# Filter HWM collection
def filter_hwm(collection: pystac.Collection, hucs: List[str]) -> Dict[str, Dict[str, Dict[str, Union[List[str], gpd.GeoDataFrame]]]]:
    result = defaultdict(lambda: defaultdict(dict))
    
    # Iterate over items in the top-level collection
    for item in collection.get_items():
        item_id = item.id
        item_hucs = item.properties.get("hucs", [])
        matching_hucs = [huc for huc in item_hucs if huc in hucs]
        
        # If the item matches any of the provided HUCs, process it
        if matching_hucs:
            # Get flowfile asset if it exists and doesn't contain "None" in the href
            flowfile_asset = next((asset for asset_key, asset in item.assets.items() 
                                   if "flowfile" in asset_key.lower()), None)
            if flowfile_asset and "None" not in flowfile_asset.href:
                # Process item's geometry
                geometry = item.geometry
                if geometry and geometry["type"] == "MultiPoint":
                    points = [Point(coord) for coord in geometry["coordinates"]]
                    gdf = gpd.GeoDataFrame(geometry=points, crs="EPSG:4326")
                    # Add attribute that marks presence of water for gval
                    gdf['class_value'] = 1

                    # Add results for each matching HUC
                    for huc in matching_hucs:
                        result[huc][item_id] = {
                            "flowfiles": [flowfile_asset.href],
                            "points": gdf
                        }
    
    return defaultdict_to_dict(result)

def get_huc_gdf(huc: str, eval_catalog: Dict) -> gpd.GeoDataFrame:
    huc_shape_path = None
    
    for shape_info in eval_catalog.get('huc8Shapes', []):
        if shape_info['huc'] == huc:
            huc_shape_path = os.path.join(shape_info['dir_path'], shape_info['filename'])
            break
    
    if not huc_shape_path:
        raise ValueError(f"HUC shape file not found for HUC {huc}")
    
    huc_gdf = gpd.read_file(get_local_filepath(huc_shape_path, WORK_DIR))
    return huc_gdf.to_crs('EPSG:4326')

def get_huc_tiles(huc: str, eval_catalog: Dict, get_huc_gdf: callable) -> List[str]:
    huc_wpj = get_huc_gdf(huc, eval_catalog)
    huc_geom = huc_wpj['geometry'].iloc[0]
    wkt_huc = huc_geom.wkt
    ogr_huc = ogr.CreateGeometryFromWkt(wkt_huc)

    # Get Equi7Grid tiles
    huc_tiles = Equi7Grid(20).search_tiles_in_roi(ogr_huc, coverland=True)
    huc_tile_ids = [tile.split('_')[-1] for tile in huc_tiles]

    return huc_tile_ids

def filter_gfm(collection: pystac.Collection, tile_ids: List[str]) -> Dict[str, Dict[str, List[str]]]:
    result = defaultdict(lambda: {"flowfiles": [], "extents": []})
    
    for item in collection.get_items():
        dfo_event_id = item.properties.get("dfo_event_id")
        equi7tile_assets = item.properties.get("equi7tile_assets", {})
        
        for tile_id in equi7tile_assets.keys():
            if tile_id in tile_ids:
                # Add extents
                extent_asset_key = f"{tile_id}_Observed_Water_Extent"
                extent_asset = item.assets.get(extent_asset_key)
                if extent_asset:
                    result[dfo_event_id]["extents"].append(extent_asset.href)
                
                # Add flowfiles
                flowfile_asset = next((asset for asset_key, asset in item.assets.items() 
                                       if "flowfile" in asset_key.lower()), None)
                if flowfile_asset:
                    result[dfo_event_id]["flowfiles"].append(flowfile_asset.href)
    
    return dict(result)

def get_eval_catalog_data(eval_catalog: Dict, hucs: List[str]) -> Dict[str, Dict[str, Dict[str, List[str]]]]:
    temp_result = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    
    for key, value in eval_catalog.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            for item in value:
                if 'huc' in item and item['huc'] is not None and 'data_version' in item:
                    version = item['data_version']
                    huc = item['huc']
                    if hucs == ["all"] or huc in hucs:
                        filepath = os.path.join(item.get('dir_path', ''), item.get('filename', ''))
                        temp_result[version][huc][key].append(filepath)
    
    return defaultdict_to_dict(temp_result)

def get_stac_catalog_data(
    stac_catalog: pystac.Catalog,
    benchmark_categories: List[str],
    hucs: List[str],
    eval_cat: Dict
) -> Dict[str, Dict[str, Dict[str, Union[Dict[str, List[str]], gpd.GeoDataFrame]]]]:
    def lid_dict():
        return {"flowfiles": [], "extents": []}
    
    def ble_dict():
        return defaultdict(lambda: {"flowfiles": [], "extents": []})
    
    result = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(lid_dict))))
    
    for collection in stac_catalog.get_children():
        collection_id = collection.id.lower()

        if 'ble' in collection_id and 'ble' in benchmark_categories:
            ble_result = defaultdict(lambda: defaultdict(ble_dict))
            for item in collection.get_items():
                process_item(item, 'ble', ble_result)
            for huc in ble_result:
                result[huc] = defaultdict_to_dict(ble_result[huc])

        elif 'gfm' in collection_id and 'gfm' in benchmark_categories:
            for huc in hucs:
                huc_tile_ids = get_huc_tiles(huc, eval_cat, get_huc_gdf)
                gfm_data = filter_gfm(collection, huc_tile_ids)
                result[huc]['gfm'] = gfm_data

        elif 'hwm' in collection_id and 'hwm' in benchmark_categories:
            hwm_data = filter_hwm(collection, hucs)
            for huc, huc_data in hwm_data.items():
                result[huc]['hwm'] = huc_data

    if not result:
        raise ValueError(f"No data found in stac_catalog for benchmark categories: {benchmark_categories} and HUCs: {hucs}")

    return defaultdict_to_dict(result)

def get_eval_data(eval_catalog: Dict, stac_catalog: pystac.Catalog, benchmark_categories: List[str], hucs: List[str] = ["all"]) -> Dict[str, Dict[str, Dict[str, Dict[str, List[str]]]]]:
    if "all" in benchmark_categories:
        benchmark_categories = list(MAGNITUDE_DICT.keys())

    eval_data = get_eval_catalog_data(eval_catalog, hucs)
    stac_data = get_stac_catalog_data(stac_catalog, benchmark_categories, hucs, eval_catalog)
   
    result = defaultdict(lambda: defaultdict(dict))
    
    for version, hucs_data in eval_data.items():
        for huc, data_types in hucs_data.items():
            result[version][huc]['hand'] = data_types
    
    for huc in stac_data.keys():
        for version in result.keys():
            if huc in result[version]:
                result[version][huc].update(stac_data[huc])
    
    if not result:
        raise ValueError(f"No common data found between eval_catalog and stac_catalog for benchmark categories: {benchmark_categories} and HUCs: {hucs}")
    
    return defaultdict_to_dict(result)
