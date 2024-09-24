#!/usr/bin/env python3
import pdb
import argparse
import os
import pystac

from inundation import inundate
from mosaic_inundation import Mosaic_inundation
from cat_query import get_eval_data, load_eval_cat, load_stac 
import cat_eval
from tools_shared_variables import INPUTS_DIR, WORK_DIR
from tools_shared_functions import compute_contingency_stats_from_rasters, get_local_filepath

def parse_list_arg(arg_value):
    if arg_value.lower() == "all":
        return ["all"]
    return [item.strip() for item in arg_value.split(',') if item.strip()]


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
        help='Comma-separated list of benchmark categories to specify. Use "all" for all categories. Don\'t use spaces after commas.',
        required=False,
        default="all",
    )
    parser.add_argument(
        '-hu',
        '--hucs',
        help='Comma-separated list of HUC8 codes to process. Use "all" for all HUCs. Don\'t use spaces after commas.',
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
    args = parser.parse_args()
    fim_version = args.fim_version
    benchmark_category = parse_list_arg(args.benchmark_category)
    hucs = parse_list_arg(args.hucs)
    config = args.config
    calibrated = args.calibrated
    model = args.model
    master_metrics_csv = args.master_metrics_csv

    # load in catalogs
    evalcat_path = os.path.join("/data/", "test_oe_cat.json")
    benchcat_path = os.path.join("/data/", "bench_stac","catalog.json")
    evalcat = load_eval_cat(evalcat_path)
    benchcat = load_stac(benchcat_path)

    # mosaic and inundate
    filt_cat_dict = get_eval_data(evalcat, benchcat, benchmark_category, hucs)
    reach_extents_df  = cat_eval.cat_inundate(filt_cat_dict, inundate)
    hand_extents = cat_eval.mosaic_branch_groups(reach_extents_df,Mosaic_inundation)

    #make mask_dict
    # mask_dict will be moved to a data class with accompanying method to update in cat_eval.py eventually.
    # get local vector paths if not in data
    levee_path = get_local_filepath("/data/nld_vectors/Levee_protected_areas.gpkg",WORK_DIR)
    water_bod_path = get_local_filepath("/data/nwm_hydrofabric/nwm_lakes.gpkg",WORK_DIR)

    # Create list of shapefile paths to use as exclusion areas.
    mask_dict = {
        "levees": {
            "path": levee_path,
            "buffer": None,
            "operation": "exclude",
        },
        "waterbodies": {
            "path": water_bod_path,
            "buffer": None,
            "operation": "exclude",
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
         work_dir=WORK_DIR,
         eval_catalog=evalcat
     )

    if master_metrics_csv:
        eval_metrics_df.to_csv(master_metrics_csv, index=False)
        print(f"eval metrics written to {master_metrics_csv}")
