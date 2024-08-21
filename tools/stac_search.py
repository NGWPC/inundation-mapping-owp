from osgeo import ogr
import pdb
import re
import pystac
import os
import json
import boto3
from urllib.parse import urlparse
from equi7grid.equi7grid import Equi7Grid
from collections import defaultdict
import rasterio
from rasterio.merge import merge
from rasterio.mask import mask
import rioxarray
from rioxarray.exceptions import NoDataInBounds
from shapely.geometry import mapping, box
import xarray as xr
import geopandas as gpd
import pandas as pd
import numpy as np
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

def process_gfm_flowfiles(event_directory):
    flowfiles = [os.path.join(event_directory, f) for f in os.listdir(event_directory) if f.endswith('.csv')]
    if not flowfiles:
        return None

    # Read and combine all flowfiles
    dfs = []
    for file in flowfiles:
        df = pd.read_csv(file, header=None, names=['col1', 'col2'])
        dfs.append(df)
    
    combined_df = pd.concat(dfs, ignore_index=True)

    # Deduplicate rows based on the first column, keeping the maximum value in the second column
    combined_df = combined_df.groupby('col1', as_index=False)['col2'].max()

    # Write the combined flowfile
    output_file = os.path.join(event_directory, "combined_flowfile.csv")
    combined_df.to_csv(output_file, index=False, header=False)

def mosaic_gfm(raster_files, huc_geom, output_directory, output_filename="mosaiced.tif", nodata_value=255):
    '''
    arguments:
    nodata_value: set this to the nodata_value of the gfm observed water extents (this is usually 255)
    '''
    huc_bounds = huc_geom.bounds
    bounding_box = box(*huc_bounds)
    
    bbox_gdf = gpd.GeoDataFrame({"geometry": [bounding_box]}, crs="EPSG:4326")
    
    aligned_rasters = []
    
    for i, raster_file in enumerate(raster_files):
        raster = rioxarray.open_rasterio(raster_file, masked=True)

        if i == 0:
            reference_raster = raster.rio.clip(bbox_gdf.geometry.apply(mapping), bbox_gdf.crs, drop=True, invert=False)
            reference_raster = reference_raster.where(reference_raster != nodata_value)
            aligned_rasters.append(reference_raster)
        else:
            try:
                clipped_raster = raster.rio.clip(bbox_gdf.geometry.apply(mapping), bbox_gdf.crs, drop=True, invert=False)
                aligned_raster = clipped_raster.rio.reproject_match(reference_raster)
                aligned_raster = aligned_raster.where(aligned_raster != nodata_value)
                aligned_rasters.append(aligned_raster)
            except NoDataInBounds:
                print(f"No data found in bounds for raster {raster_file}. Skipping...")

    if not aligned_rasters:
        print("No rasters with data in bounds were found.")
        return None

    stacked_rasters = xr.concat(aligned_rasters, dim="stack")
    max_raster = stacked_rasters.max(dim="stack", skipna=True)
    max_raster = max_raster.where(~max_raster.isnull(), nodata_value)
    huc_gdf = gpd.GeoDataFrame({"geometry": [huc_geom]}, crs="EPSG:4326")
    
    if huc_gdf.crs != max_raster.rio.crs:
        huc_gdf = huc_gdf.to_crs(max_raster.rio.crs)

    max_raster = max_raster.rio.clip(huc_gdf.geometry.apply(mapping), huc_gdf.crs, drop=True, invert=False)
    max_raster.rio.write_nodata(nodata_value, inplace=True)

    os.makedirs(output_directory, exist_ok=True)

    output_path = os.path.join(output_directory, output_filename)
    max_raster.rio.to_raster(output_path)

    return output_path

def filter_and_mosaic_gfm(collection, tile_ids, output_directory, huc_geom):
    # Initialize the result dictionaries
    search_result = defaultdict(lambda: defaultdict(list))
    mosaiced_files = {}
    combined_flowfiles = {}

    # Iterate through all items in the collection
    for item in collection.get_items():
        dfo_event_id = item.properties.get("dfo_event_id")
        equi7tile_assets = item.properties.get("equi7tile_assets", {})

        for tile_id in equi7tile_assets.keys():
            if tile_id in tile_ids:
                search_result[dfo_event_id][tile_id].append(item.id)

                # Create a subdirectory for this event
                event_directory = os.path.join(output_directory, dfo_event_id)
                os.makedirs(event_directory, exist_ok=True)

                # Download Observed Water Extent asset
                asset_key = f"{tile_id}_Observed_Water_Extent"
                if asset_key in item.assets:
                    try:
                        download_s3_asset(item.assets[asset_key].href, event_directory)
                        print(f"Downloaded {asset_key} for item {item.id}")
                    except Exception as e:
                        print(f"Error downloading {asset_key} for item {item.id}: {str(e)}")
                else:
                    print(f"Asset {asset_key} not found for item {item.id}")

                # Download Flowfile asset
                flowfile_asset = next((asset for asset_key, asset in item.assets.items() if "flowfile" in asset_key.lower()), None)

                if flowfile_asset:
                    try:
                        download_s3_asset(flowfile_asset.href, event_directory)
                        print(f"Downloaded flowfile for item {item.id}")
                    except Exception as e:
                        print(f"Error downloading flowfile for item {item.id}: {str(e)}")
                else:
                    print(f"Flowfile asset not found for item {item.id}")
    # Process rasters and flowfiles for each event
    for event_id, tiles in search_result.items():
        event_directory = os.path.join(output_directory, event_id)

        # Mosaic and mask rasters
        raster_files = [os.path.join(event_directory, f) for f in os.listdir(event_directory) if f.endswith('.tif')]
        
        if raster_files:
            mosaiced_file = mosaic_gfm(raster_files, huc_geom, event_directory)
            mosaiced_files[event_id] = mosaiced_file
        else:
            print(f"No raster files found for event {event_id}")

        pdb.set_trace()
        # Process flowfiles
        flowfile_path = process_gfm_flowfiles(event_directory)
        if flowfile_path:
            combined_flowfiles[event_id] = flowfile_path
        else:
            print(f"No flowfiles found for event {event_id}")

    return mosaiced_file, combined_flowfiles

def get_bench_asset(catalog, bench_cat, asset_type, huc, huc_gdf, lid=None, magnitude=None):
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

    # ble, usgs, and nws collection seach
    if any(substring in bench_cat for substring in ["ble", "usgs", "nws"]):
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


    # search through gfm data
    if "gfm" in bench_cat:
        # use huc geometry as input to return tiles in a huc. Pretty sure Equi7Grid package expects an OGR geometry but if not try the geodataframes shapely geometry
        huc_wpj = huc_gdf.to_crs('EPSG:4326')
        huc_geom = huc_wpj['geometry'].iloc[0]
        wkt_huc = huc_geom.wkt
        ogr_huc = ogr.CreateGeometryFromWkt(wkt_huc)
        huc_tiles = Equi7Grid(20).search_tiles_in_roi(ogr_huc, coverland=True)
        huc_tile_ids = [tile.split('_')[-1] for tile in huc_tiles]

        # get a collated masked raster that match the equi7grid tiles in the huc
        gfm_mosaic_paths, flow_file = filter_and_mosaic_gfm(target_collection, huc_tile_ids, WORK_DIR, huc_geom)
        if asset_type == "extent":
            return gfm_mosaic_paths 
        elif asset_type == "flow":
            return flow_file
