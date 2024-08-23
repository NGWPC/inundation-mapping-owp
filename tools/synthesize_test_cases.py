#!/usr/bin/env python3
import pdb
import argparse
import ast
import csv
import json
import os
import re
import signal
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed, wait
from datetime import datetime
from multiprocessing import Pool

import pandas as pd
from run_test_case import Test_Case
from tools_shared_variables import (
    AHPS_BENCHMARK_CATEGORIES,
    MAGNITUDE_DICT,
    OUTPUTS_DIR,
    PREVIOUS_FIM_DIR,
    TEST_CASES_DIR,
    EVAL_METRICS_PATH
)
from tqdm import tqdm

from utils.shared_functions import FIM_Helpers as fh

def progress_bar_handler(executor_dict, verbose, desc):
    for future in tqdm(
        as_completed(executor_dict), total=len(executor_dict), disable=(not verbose), desc=desc
    ):
        try:
            future.result()
        except Exception as exc:
            print('{}, {}, {}'.format(executor_dict[future], exc.__class__.__name__, exc))


if __name__ == '__main__':
    # Sample usage:
    '''
     === FOR (FIM 4)
    python /foss_fim/tools/synthesize_test_cases.py
        -c DEV
        -e GMS
        -v gms_test_synth_combined
        -jh 2 -jb 40
        -m /outputs/gms_test_synth_combined/gms_synth_metrics.csv
        -vg -o

     Notes:
       - fim_input.csv MUST be in the folder suggested.
       - the -v param is the name in the folder in the "outputs/" directory where the test hucs are at.
         It also becomes the folder names inside the test_case folders when done.
       - the -vg param may not be working (will be assessed better on later releases).
       - Find a balance between -jh (number of jobs for hucs) versus -jb (number of jobs for branches)
         on quick tests on a 96 core machine, we tried [1 @ 80], [2 @ 40], and [3 @ 25] (and others).
       -jb 3 -jh 25 was noticably better. You can likely go more jb cores with better success, just
         experiment.  Start times, End Times and duration are now included.
       - The -m can be any path and any name.
       - Previous metric CSV (-pcsv) and the cycle previous files argument (-pfiles) will return an error
         if called at the same time. If neither are used, the alpha test metrics will only be compiled
         for the provided dev version to compare.

     To see your outputs in the test_case folder (hard coded path), you can check for outputs using
         (cd .... to your test_case folder), then command becomes  find . -name gms_test_* -type d (Notice the
         the -name can be a wildcard for your -v param (or the whole -v value))
     If you want to delete the test outputs, test the outputs as suggest immediately above, but this time your
         command becomes:  find . -name gms_test_* -type d  -exec rm -rdf {} +
    '''
    '''
     === FOR FIM 3
    python /foss_fim/tools/synthesize_test_cases.py
        -c DEV
        -e MS
        -v dev_fim_3_0_29_1_ms
        -jh 4
        -m /outputs/dev_fim_3_0_29_1_ms/alpha/alpha_master_metrics_fim_3_0_29_1_ms_src_adjust.csv
        -vg -o

     Notes:
       - the -v param is the name in the folder in the "outputs/" directory where the test hucs are at.
           It also becomes the folder names inside the test_case folders when done.
       - the -vg param may not be working (will be assessed better on later releases).
       - The -m can be any path and any name.

     To see your outputs in the test_case folder (hard coded path), you can check for outputs using
         (cd .... to your test_case folder), then command becomes  find . -name dev_fim_3_0_29_1_* -type d
         (Notice the the -name can be a wildcard for your -v param (or the whole -v value))
     If you want to delete the test outputs, test the outputs as suggest immediately above, but this time your
         command becomes:  find . -name dev_fim_3_0_29_1_* -type d  -exec rm -rdf {} +
    '''

    # Parse arguments.
    parser = argparse.ArgumentParser(description='Caches metrics from previous versions of HAND.')
    parser.add_argument(
        '-c',
        '--config',
        help='Save outputs to development_versions or previous_versions? Options: "DEV" or "PREV"',
        required=True,
        default='DEV',
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
        '-v', '--fim-version', help='Name of fim version to cache.', required=False, default="all"
    )
    parser.add_argument(
        '-jh',
        '--job-number-huc',
        help='Number of processes to use for HUC scale operations. HUC and Batch job numbers should multiply '
        'to no more than one less than the CPU count of the machine.',
        required=False,
        default=1,
        type=int,
    )
    parser.add_argument(
        '-jb',
        '--job-number-branch',
        help='Number of processes to use for Branch scale operations. HUC and Batch job numbers should '
        'multiply to no more than one less than the CPU count of the machine.',
        required=False,
        default=1,
        type=int,
    )
    parser.add_argument(
        '-b',
        '--benchmark-category',
        help='A benchmark category to specify. Defaults to process all categories.',
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
        '-o',
        '--overwrite',
        help='Overwrite all metrics or only fill in missing metrics.',
        required=False,
        action="store_true",
    )
    parser.add_argument(
        '-d',
        '--fr-run-dir',
        help='Name of test case directory containing FIM for FR model',
        required=False,
        default=None,
    )
    parser.add_argument(
        '-vr', '--verbose', help='Verbose output', required=False, default=None, action='store_true'
    )
    parser.add_argument(
        '-vg',
        '--gms-verbose',
        help='GMS Verbose Progress Bar',
        required=False,
        default=None,
        action='store_true',
    )

    # Assign variables from arguments.
    args = vars(parser.parse_args())
    config = args['config']
    fim_version = args['fim_version']
    job_number_huc = args['job_number_huc']
    job_number_branch = args['job_number_branch']
    benchmark_category = args['benchmark_category']
    overwrite = args['overwrite']
    fr_run_dir = args['fr_run_dir']
    calibrated = args['calibrated']
    model = args['model']
    verbose = bool(args['verbose'])
    gms_verbose = bool(args['gms_verbose'])

    print("================================")
    print("Start synthesize test cases")
    start_time = datetime.now()
    dt_string = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    print(f"started: {dt_string}")
    print()

    # check job numbers
    total_cpus_requested = job_number_huc * job_number_branch
    total_cpus_available = os.cpu_count() - 1
    if total_cpus_requested > total_cpus_available:
        raise ValueError(
            'The HUC job number, {}, multiplied by the branch job number, {}, '
            'exceeds your machine\'s available CPU count minus one. '
            'Please lower the job_number_huc or job_number_branch'
            'values accordingly.'.format(job_number_huc, job_number_branch)
        )
    # Define whether or not to archive metrics in "official_versions" or "testing_versions" for each test_id.
    if config == 'PREV':
        archive_results = True
    elif config == 'DEV':
        archive_results = False
    else:
        print('Config (-c) option incorrectly set. Use "DEV" or "PREV"')

    # Create a list of all test_cases for which we have validation data
    all_test_cases = Test_Case.list_all_test_cases(
        version=fim_version,
        archive=archive_results,
        benchmark_categories=[] if benchmark_category == "all" else [benchmark_category],
    )

    # print('all test cases', all_test_cases)
    all_run_metrics = []

    # # Set up multiprocessor
    # with ProcessPoolExecutor(max_workers=job_number_huc) as executor:
    #     # Loop through all test cases, build the alpha test arguments, and submit them to the process pool
    #     executor_dict = {}

    #     for test_case_class in all_test_cases:
    #         if not os.path.exists(test_case_class.fim_dir):
    #             continue

    #         fh.vprint(f"test_case_class.test_id is {test_case_class.test_id}", verbose)

    #         alpha_test_args = {
    #             'calibrated': calibrated,
    #             'model': model,
    #             'mask_type': 'huc',
    #             'overwrite': overwrite,
    #             'verbose': gms_verbose if model == 'GMS' else verbose,
    #             'gms_workers': job_number_branch,
    #         }

    #         try:
    #             future = executor.submit(test_case_class.alpha_test, **alpha_test_args)
    #             executor_dict[future] = test_case_class.test_id
    #         except Exception as ex:
    #             print(f"*** {ex}")
    #             traceback.print_exc()
    #             sys.exit(1)

    #     for future in as_completed(executor_dict):
    #         test_id = executor_dict[future]
    #         try:
    #             all_flat_stats = future.result()
    #             if all_flat_stats:
    #                 all_run_metrics.extend(all_flat_stats)
    #         except Exception as ex:
    #             print(f"*** Error processing test case {test_id}: {ex}")
    #             traceback.print_exc()

    #     # Send the executor to the progress bar and wait for all MS tasks to finish
    #     progress_bar_handler(
    #         executor_dict, True, f"Running {model} alpha test cases with {job_number_huc} workers"
    #     )
    #    # wait(executor_dict.keys())

    # run test case without futures for debugging
    for test_case_class in all_test_cases:
        if not os.path.exists(test_case_class.fim_dir):
            continue
        fh.vprint(f"test_case_class.test_id is {test_case_class.test_id}", verbose)
        all_flat_stats = test_case_class.alpha_test(calibrated=calibrated,model=model,mask_type='huc',overwrite=overwrite,verbose=gms_verbose,gms_workers=1)
        all_run_metrics.extend(all_flat_stats)

    # Separate the primary key columns
    primary_keys = ['version', 'ver_env','lid','magnitude','huc','benchmark_source','extent_config','calibrated']

    # Check if the metrics file exists
    if not os.path.exists(EVAL_METRICS_PATH ):
        if all_run_metrics:
            additional_keys = [key for key in all_run_metrics[0].keys() if key not in primary_keys]
            headers = primary_keys + additional_keys
            df = pd.DataFrame(columns=headers)
            df.to_csv(EVAL_METRICS_PATH, index=False)
        else:
            raise ValueError("all_run_metrics is empty, cannot determine additional keys for headers.")
    else:
        # Load the CSV file into a pandas DataFrame
        df = pd.read_csv(EVAL_METRICS_PATH)

    for flat_stats in all_run_metrics:
        # Separate the primary key values and metric values
        primary_key_values = {key: flat_stats[key] for key in primary_keys}
        metric_values = {key: flat_stats[key] for key in flat_stats.keys() if key not in primary_keys}
    
        # Check if the row already exists
        exists = df.loc[(df[list(primary_key_values)] == pd.Series(primary_key_values)).all(axis=1)]
    
        if not exists.empty:
            # If the row exists, update it
            for key, value in metric_values.items():
                df.loc[(df[list(primary_key_values)] == pd.Series(primary_key_values)).all(axis=1), key] = value
        else:
            # If the row does not exist, insert a new row
            new_row = pd.DataFrame([{**primary_key_values, **metric_values}])
            df = pd.concat([df, new_row], ignore_index=True)

    # Write the updated DataFrame back to the CSV file
    df.to_csv(EVAL_METRICS_PATH, index=False)

    # Composite alpha test run is initiated by a MS `model` and providing a `fr_run_dir`
    if model == 'MS' and fr_run_dir:
        # Rebuild all test cases list with the FR version, loop through them and apply the alpha test
        all_test_cases = Test_Case.list_all_test_cases(
            version=fr_run_dir,
            archive=archive_results,
            benchmark_categories=[] if benchmark_category == "all" else [benchmark_category],
        )

        with ProcessPoolExecutor(max_workers=job_number_huc) as executor:
            executor_dict = {}
            for test_case_class in all_test_cases:
                if not os.path.exists(test_case_class.fim_dir):
                    continue
                alpha_test_args = {
                    'calibrated': calibrated,
                    'model': model,
                    'mask_type': 'huc',
                    'verbose': verbose,
                    'overwrite': overwrite,
                }
                try:
                    future = executor.submit(test_case_class.alpha_test, **alpha_test_args)
                    executor_dict[future] = test_case_class.test_id
                except Exception as ex:
                    print(f"*** {ex}")
                    traceback.print_exc()
                    sys.exit(1)

            # Send the executor to the progress bar and wait for all FR tasks to finish
            progress_bar_handler(executor_dict, True, f"Running FR test cases with {job_number_huc} workers")
            # wait(executor_dict.keys())

        # Loop through FR test cases, build composite arguments, and
        #   submit the composite method to the process pool
        with ProcessPoolExecutor(max_workers=job_number_huc) as executor:
            executor_dict = {}
            for test_case_class in all_test_cases:
                composite_args = {
                    'version_2': fim_version,  # this is the MS version name since `all_test_cases` are FR
                    'calibrated': calibrated,
                    'overwrite': overwrite,
                    'verbose': verbose,
                }

                try:
                    future = executor.submit(test_case_class.alpha_test, **alpha_test_args)
                    executor_dict[future] = test_case_class.test_id
                except Exception as ex:
                    print(f"*** {ex}")
                    traceback.print_exc()
                    sys.exit(1)

            # Send the executor to the progress bar
            progress_bar_handler(
                executor_dict, verbose, f"Compositing test cases with {job_number_huc} workers"
            )
    print("================================")
    print("End synthesize test cases")

    end_time = datetime.now()
    dt_string = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    print(f"ended: {dt_string}")

    # Calculate duration
    time_duration = end_time - start_time
    print(f"Duration: {str(time_duration).split('.')[0]}")
    print()
