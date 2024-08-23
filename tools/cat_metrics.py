#!/usr/bin/env python3
import pdb
import argparse
import os

from inundation import inundate
from mosaic_inundation import Mosaic_inundation
from cat_query import get_eval_data, load_eval_cat, load_flat_bench 
import cat_eval
from tools_shared_variables import INPUTS_DIR, WORK_DIR
from tools_shared_functions import compute_contingency_stats_from_rasters, get_local_filepath

if __name__ == '__main__':
    # Parse arguments.
    parser = argparse.ArgumentParser(description='Caches metrics from previous versions of HAND.')
    parser.add_argument(    
        '-v', '--fim-version', help='List of fim versions to cache.', required=False, default="all"
    )
    parser.add_argument(
        '-c',
        '--config',
        help='Save outputs to development_versions or previous_versions? Options: "DEV" or "PREV"',
        required=True,
        default='DEV',
    )
    parser.add_argument(
        '-b',
        '--benchmark-category',
        help='A list of benchmark category to specify. Defaults to process all categories.',
        required=False,
        default="all",
    )
    parser.add_argument(
        '-hu',
        '--hucs',
        help='Comma-separated list of HUC8 codes to process',
        required=False,
        default="all",
    )
    parser.add_argument(
        '-l',
        '--calibrated',
        help='Denotes use of calibrated n values. This should be taken from meta-data from hydrofabric dir',
        required=False,
        default=False,
        action='store_true',
    )
    parser.add_argument(
        '-e',
        '--model',
        help='Denotes model used. Options: [FR, MS, or GMS]. '
        'This should be taken from meta-data in hydrofabric dir.',
        default='GMS',
        required=False,
    )
    parser.add_argument(
        '-m',
        '--master-metrics-csv',
        help='Define path for master metrics CSV file.',
        required=False,
        default=None,
    )

    # Assign variables from arguments.
    args = vars(parser.parse_args())
    fim_version = args['fim_version']
    config = args['config']
    benchmark_category = args['benchmark_category'] #TODO: make sure benchmark_category is read in as a list
    hucs = args['hucs']
    calibrated = args['calibrated']
    model = args['model']
    master_metrics_csv = args['master_metrics_csv']

    # load in catalogs
    evalcat_path = os.path.join(INPUTS_DIR, "test_eval_cat.json")
    benchcat_path = os.path.join(INPUTS_DIR, "flatcat.msgpack")
    evalcat = load_eval_cat(evalcat_path)
    benchcat = load_flat_bench(benchcat_path)

    #TODO: add in hucs and fim_version to get_eval_data as well as ["all"] fallbacks for each source
    filt_cat_dict = get_eval_data(evalcat, benchcat, ["ble"])
    reach_extents_df  = cat_eval.cat_inundate(filt_cat_dict, inundate)
    hand_extents = cat_eval.mosaic_branch_groups(reach_extents_df,Mosaic_inundation)

    #make mask_dict
    # mask_dict will be moved to a data class with accompanying method to update in cat_eval.py eventually.
    # get local vector paths if not in data
    levee_path = get_local_filepath("s3://noaa-nws-owp-fim/hand_fim/inputs/nld_vectors/Levee_protected_areas.gpkg",WORK_DIR)
    water_bod_path = get_local_filepath("s3://noaa-nws-owp-fim/hand_fim/inputs/nwm_hydrofabric/nwm_lakes.gpkg",WORK_DIR)    

    # Create list of shapefile paths to use as exclusion areas.
    mask_dict = {
        'levees': {
            'path': levee_path,
            'buffer': None,
            'operation': 'exclude',
        },
        'waterbodies': {
            'path': water_bod_path,
            'buffer': None,
            'operation': 'exclude',
        },
    }

eval_metrics_df = cat_eval.get_eval_metrics(
     data=filt_cat_dict ,
     compute_contingency_stats_from_rasters=compute_contingency_stats_from_rasters,
     extent_paths=hand_extents,
     mask_dict=mask_dict,
     archive=config,
     model=model,
     calibrated=calibrated,
     work_dir=WORK_DIR
 )

if master_metrics_csv:
    eval_metrics_df.to_csv(master_metrics_csv, index=False)
    print(f"eval metrics written to written to {master_metrics_csv}")
