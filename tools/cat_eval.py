import os
import pandas as pd
from typing import Dict, Any, List
import json

from tools_shared_variables import WORK_DIR

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
    
def cat_inundate(data: Dict[str, Any], inundate: callable) -> pd.DataFrame:
    """
    Process flood inundation data and generate inundation rasters.
    
    :param data: Nested dictionary containing flood data
    :param inundate_gms: Function to generate inundation rasters
    :return: Path to the CSV file containing all output paths
    """
    output_paths = []
    
    for version, hucs in data.items():
        for huc_code, huc_data in hucs.items():
            hand_data = huc_data['hand']
            
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
                        for magnitude, magnitude_data in value.items():
                            for flowfile in magnitude_data['flowfiles']:

                                # Construct output path and directory
                                output_path = f"{WORK_DIR}/test_cases/{key}/{huc_code}/{version}/{magnitude}/{branch_id}_inundation.tif"
                                directory = os.path.dirname(output_path)
                                os.makedirs(directory, exist_ok=True)

                                inundate(
                                    rem=rem,
                                    catchments=catchment,
                                    catchment_poly=catchment_poly,
                                    hydro_table=hydro_table,
                                    forecast=flowfile,
                                    mask_type= filter,
                                    inundation_raster=output_path
                                )

                                output_paths.append({
                                    'huc8': huc_code,
                                    'branchID': branch_id,
                                    'inundation_rasters': output_path
                                })

    reach_extents_df = pd.DataFrame(output_paths, columns=['huc8', 'branchID', 'inundation_rasters'])
    
    return reach_extents_df

def get_eval_metrics(data: Dict[str, Any], 
                     compute_contingency_stats_from_rasters: callable,
                     extent_paths: List[str],
                     mask_dict: Dict[str, Any],
                     archive: str,
                     model: str,
                     calibrated: str,
                     work_dir: str) -> pd.DataFrame:
    """
    Process flood inundation data and compute evaluation metrics.
    
    :param data: Nested dictionary containing flood data
    :param compute_contingency_stats_from_rasters: Function to compute contingency stats
    :param extent_paths: List of extent paths
    :param mask_dict: Dictionary of masks
    :param archive: Archive string
    :param model: Model string
    :param calibrated: Calibrated string
    :param work_dir: Working directory path
    :return: DataFrame containing evaluation metrics
    """
    output_metrics = []
    
    for version, hucs in data.items():
        for huc_code, huc_data in hucs.items():
              
            # Process flowfiles and extents for each non-'hand' key
            for key, value in huc_data.items():
                if key != 'hand':
                    for magnitude, magnitude_data in value.items():
                        for bench_extent in magnitude_data['extents']:
                            
                            # Construct output path and directory
                            output_path = f"{work_dir}/test_cases/{key}/{huc_code}/{version}/{magnitude}/eval_metrics.json"
                            directory = os.path.dirname(output_path)
                            os.makedirs(directory, exist_ok=True)
                            
                            # Find the matching predicted_raster_path
                            predicted_raster_path = next((path for path in extent_paths if directory in path), None)
                            if predicted_raster_path is None:
                                print(f"Warning: No matching predicted raster found for directory: {directory}")
                                continue
                            
                            # Compute contingency stats. metrics is a one level deep dictionary
                            metrics = compute_contingency_stats_from_rasters(
                                version=version,
                                lid='',  # placeholder for lid until ahps conditionals added in
                                magnitude=magnitude,
                                huc=huc_code,
                                archive=archive,
                                benchmark_raster_path=bench_extent,
                                predicted_raster_path=predicted_raster_path,
                                agreement_raster=os.path.join(directory, "agreement_raster"),
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

