import os
import pdb
import pandas as pd
from typing import Dict, Any, List
import json
import numpy as np
import geopandas as gpd
from shapely.geometry import box
from shapely.geometry import mapping
import rioxarray
import xarray as xr
from rioxarray.exceptions import NoDataInBounds

from cat_query import get_huc_gdf
from tools_shared_functions import get_local_filepath
from tools_shared_variables import WORK_DIR

def mosaic_gfm(raster_files, huc_gdf, output_directory, output_filename="mosaiced.tif", nodata_value=255):
    if len(huc_gdf) != 1:
        raise ValueError("The huc_gdf should contain exactly one geometry.")

    huc_bounds = huc_gdf.total_bounds
    bounding_box = box(*huc_bounds)
    
    bbox_gdf = gpd.GeoDataFrame({"geometry": [bounding_box]}, crs=huc_gdf.crs)
    
    aligned_rasters = []
    
    for raster_file in raster_files:
        try:
            raster = rioxarray.open_rasterio(raster_file, masked=True)
            clipped_raster = raster.rio.clip(bbox_gdf.geometry.apply(mapping), bbox_gdf.crs, drop=True, invert=False)
            
            if clipped_raster.rio.nodata is not None:
                clipped_raster = clipped_raster.where(clipped_raster != clipped_raster.rio.nodata)
            else:
                clipped_raster = clipped_raster.where(clipped_raster != nodata_value)
            
            if not clipped_raster.isnull().all():
                if not aligned_rasters:
                    reference_raster = clipped_raster
                else:
                    clipped_raster = clipped_raster.rio.reproject_match(reference_raster)
                    clipped_raster = clipped_raster.where(clipped_raster < 5)
                aligned_rasters.append(clipped_raster)
        except Exception as e:
            print(f"Error processing raster {raster_file}: {str(e)}. Skipping...")
    
    if not aligned_rasters:
        print("No rasters with data in bounds were found.")
        return None
    
    stacked_rasters = xr.concat(aligned_rasters, dim="band")
    max_raster = stacked_rasters.max(dim="band", skipna=True)
    max_raster = max_raster.where(~max_raster.isnull(), nodata_value)
    
    if huc_gdf.crs != max_raster.rio.crs:
        huc_gdf = huc_gdf.to_crs(max_raster.rio.crs)
    
    max_raster = max_raster.rio.clip(huc_gdf.geometry.apply(mapping), huc_gdf.crs, drop=True, invert=False)
    max_raster.rio.write_nodata(nodata_value, inplace=True)
    
    os.makedirs(output_directory, exist_ok=True)
    output_path = os.path.join(output_directory, output_filename)
    max_raster.rio.to_raster(output_path)
    return output_path

def mosaic_branch_groups(df: pd.DataFrame, Mosaic_inundation: callable):
    """
    Group the dataframe by dirpath and process each group using Mosaic_inundation.
    
    :param df: DataFrame containing the output paths
    :param process_function: Function to process each group of data
    """
    # Extract dirpath from the full path
    df['dirpath'] = df['inundation_rasters'].apply(os.path.dirname)
    
    # Group by dirpath
    grouped = df.groupby('dirpath')

    hand_extent_paths = []    
    # Process each group
    for dirpath, group_df in grouped:
        # Reset the index and drop the 'dirpath' column for the group DataFrame
        group_df = group_df.reset_index(drop=True).drop('dirpath', axis=1)
        
        # Call the process function with the group DataFrame and dirpath
        mosaiced_path = Mosaic_inundation(group_df, mosaic_attribute="inundation_rasters",mosaic_output=f"{dirpath}/inundated_extent.tif")
        hand_extent_paths.append(mosaiced_path)
    return hand_extent_paths

def process_gfm_flowfiles(gfm_data: Dict[str, Dict[str, Dict[str, List[str]]]]) -> Dict[str, Dict[str, str]]:
    combined_flowfiles = {}

    for huc, events in gfm_data.items():
        combined_flowfiles[huc] = {}
        for event_id, event_data in events.items():
            flowfiles = event_data['flowfiles']
            all_dfs = []
            header = None
            
            # read in flowfiles
            for flowfile in flowfiles:
                df = pd.read_csv(get_local_filepath(flowfile,WORK_DIR))             
                if header is None:
                    header = df.columns.tolist()
                all_dfs.append(df)

            if all_dfs:
                combined_df = pd.concat(all_dfs, ignore_index=True)
                # Deduplicate rows based on the first column, keeping the maximum value in the second column
                combined_df = combined_df.groupby(combined_df.columns[0], as_index=False)[combined_df.columns[1]].max()
                
                # Write combined flowfiles
                output_dir = os.path.join(WORK_DIR, 'combined_flowfiles', huc)
                os.makedirs(output_dir, exist_ok=True)
                output_file = os.path.join(output_dir, f"{event_id}_combined_flowfile.csv")
                combined_df.to_csv(output_file, index=False, header=header)
                
                combined_flowfiles[huc][event_id] = output_file

    return combined_flowfiles

def cat_inundate(data: Dict[str, Any], inundate: callable) -> pd.DataFrame:
    """
    Process flood inundation data and generate inundation rasters.
    
    :param data: Nested dictionary containing flood data
    :param inundate: Function to generate inundation rasters
    :return: DataFrame containing all output paths
    """
    output_paths = []
    
    for version, hucs in data.items():
        for huc_code, huc_data in hucs.items():
            hand_data = huc_data['hand']
            
            # Process GFM flowfiles if present
            if 'gfm' in huc_data:
                gfm_flowfiles = process_gfm_flowfiles({huc_code: huc_data['gfm']})
            else:
                gfm_flowfiles = {}

            # Process each REM file
            for i, rem in enumerate(hand_data['rems']):
                catchment = hand_data['reachRasters'][i]
                catchment_poly = hand_data['reachAttributes'][i]
                hydro_table = hand_data['hydroTables'][i]
                
                # Extract branch_id from the file name
                branch_id = os.path.basename(rem).split('_')[-1].split('.')[0]
                
                # Process flowfiles for each non-'hand' key
                for key, value in huc_data.items():
                    if key != 'hand':
                        if key == 'gfm':
                            for event_id, combined_flowfile in gfm_flowfiles.get(huc_code, {}).items():
                                output_path = f"{WORK_DIR}/test_cases/{key}/{huc_code}/{version}/{event_id}/{branch_id}_inundation.tif"
                                directory = os.path.dirname(output_path)
                                os.makedirs(directory, exist_ok=True)
                                inundate(
                                    rem=rem,
                                    catchments=catchment,
                                    catchment_poly=catchment_poly,
                                    hydro_table=hydro_table,
                                    forecast=combined_flowfile,
                                    mask_type='filter',
                                    inundation_raster=output_path
                                )
                                output_paths.append({
                                    'huc8': huc_code,
                                    'branchID': branch_id,
                                    'event_id': event_id,
                                    'inundation_rasters': output_path
                                })
                        else:
                            # Process other benchmark categories as before
                            for magnitude, magnitude_data in value.items():
                                for flowfile in magnitude_data['flowfiles']:
                                    output_path = f"{WORK_DIR}/test_cases/{key}/{huc_code}/{version}/{magnitude}/{branch_id}_inundation.tif"
                                    directory = os.path.dirname(output_path)
                                    os.makedirs(directory, exist_ok=True)
                                    inundate(
                                        rem=rem,
                                        catchments=catchment,
                                        catchment_poly=catchment_poly,
                                        hydro_table=hydro_table,
                                        forecast=flowfile,
                                        mask_type='filter',
                                        inundation_raster=output_path
                                    )
                                    output_paths.append({
                                        'huc8': huc_code,
                                        'branchID': branch_id,
                                        'magnitude': magnitude,
                                        'inundation_rasters': output_path
                                    })

    reach_extents_df = pd.DataFrame(output_paths)
    
    return reach_extents_df

def get_eval_metrics(
    data: Dict[str, Any],
    compute_contingency_stats_from_rasters: callable,
    extent_paths: List[str],
    mask_dict: Dict[str, Any],
    archive: str,
    model: str,
    calibrated: str,
    work_dir: str,
    eval_catalog: Dict,
) -> pd.DataFrame:
    output_metrics = []
    
    for version, hucs in data.items():
        for huc_code, huc_data in hucs.items():
            
            # Process flowfiles and extents for each non-'hand' key
            for key, value in huc_data.items():
                if key != 'hand':
                    for magnitude, magnitude_data in value.items():
                        if key == 'gfm':
                            # Mosaic GFM extents
                            huc_gdf = get_huc_gdf(huc_code, eval_catalog)
                            output_directory = f"{work_dir}/test_cases/{key}/{huc_code}/{version}/{magnitude}"
                            os.makedirs(output_directory, exist_ok=True)
                            mosaiced_extent = mosaic_gfm(magnitude_data['extents'], huc_gdf, output_directory, "gfm_mosaiced.tif")
                            
                            if mosaiced_extent is None:
                                print(f"Warning: Benchmark mosaicking failed for GFM extents in HUC {huc_code}, magnitude {magnitude}")
                                continue
                            
                            bench_extents = [mosaiced_extent]
                        elif key == 'hwm':
                            bench_extents = magnitude_data['points']
                        else:
                            bench_extents = magnitude_data['extents']
                        
                        for bench_extent in bench_extents:
                            # Construct output path and directory
                            output_path = f"{work_dir}/test_cases/{key}/{huc_code}/{version}/{magnitude}/eval_metrics.json"
                            directory = os.path.dirname(output_path)
                            os.makedirs(directory, exist_ok=True)
                            
                            # Find the matching predicted_raster_path
                            predicted_raster_path = next((path for path in extent_paths if directory in path), None)
                            if predicted_raster_path is None:
                                print(f"Warning: No matching predicted raster found for directory: {directory}")
                                continue
                            if key == 'hwm':                              
                                metrics = compute_contingency_stats_from_rasters(
                                    version=version,
                                    lid='',  # placeholder for lid until ahps conditionals added in
                                    magnitude=magnitude,
                                    huc=huc_code,
                                    archive=archive,
                                    benchmark_raster_path='',
                                    predicted_raster_path=predicted_raster_path,
                                    agreement_raster=os.path.join(directory, "agreement_raster.tif"),
                                    benchmark_points= bench_extents,
                                    bench_category=key,
                                    extent_config=model,
                                    calibrated=calibrated,
                                    mask_dict=mask_dict
                                )
                            else:
                                # Compute contingency stats
                                metrics = compute_contingency_stats_from_rasters(
                                    version=version,
                                    lid='',  # placeholder for lid until ahps conditionals added in
                                    magnitude=magnitude,
                                    huc=huc_code,
                                    archive=archive,
                                    benchmark_raster_path=bench_extent,
                                    predicted_raster_path=predicted_raster_path,
                                    agreement_raster=os.path.join(directory, "agreement_raster.tif"),
                                    bench_category=key,
                                    extent_config=model,
                                    calibrated=calibrated,
                                    mask_dict=mask_dict
                                )
                            
                            # Save individual site metrics to file
                            with open(output_path, 'w') as f:
                                json.dump(metrics, f)
                            
                            output_metrics.append(metrics)
    
    # Create DataFrame from the list of metric dictionaries
    eval_metrics_df = pd.DataFrame(output_metrics)
    
    return eval_metrics_df
