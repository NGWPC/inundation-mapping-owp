#!/usr/bin/env python3

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
        '-s',
        '--special-string',
        help='Add a special name to the end of the branch.',
        required=False,
        default="",
    )
    parser.add_argument(
        '-b',
        '--benchmark-category',
        help='A benchmark category to specify. Defaults to process all categories.',
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
        '-dc',
        '--dev-version-to-compare',
        nargs='+',
        help='Specify the name(s) of a dev (testing) version to include in master '
        'metrics CSV. Pass a space-delimited list.',
        required=False,
    )
    parser.add_argument(
        '-m',
        '--master-metrics-csv',
        help='Define path for master metrics CSV file.',
        required=False,
        default=None,
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
    parser.add_argument(
        '-pcsv',
        '--previous-metrics-csv',
        help='Optional: Filepath for a CSV with previous metrics to concatenate with new '
        'metrics to form a final aggregated metrics csv.',
        required=False,
        default=None,
    )
    parser.add_argument(
        '-pfiles',
        '--cycle-previous-files',
        help='Optional: Specifies whether previous metrics should be compiled by cycling '
        'through files (True). Cannot be used if a previous metrics CSV is provided.',
        required=False,
        action="store_true",
    )

    # Assign variables from arguments.
    args = vars(parser.parse_args())
    config = args['config']
    fim_version = args['fim_version']
    job_number_huc = args['job_number_huc']
    job_number_branch = args['job_number_branch']
    special_string = args['special_string']
    benchmark_category = args['benchmark_category']
    overwrite = args['overwrite']
    dev_versions_to_compare = args['dev_version_to_compare']
    master_metrics_csv = args['master_metrics_csv']
    fr_run_dir = args['fr_run_dir']
    calibrated = args['calibrated']
    model = args['model']
    verbose = bool(args['verbose'])
    gms_verbose = bool(args['gms_verbose'])
    prev_metrics_csv = args['previous_metrics_csv']
    pfiles = bool(args['cycle_previous_files'])

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

    # Default to processing all possible versions in PREVIOUS_FIM_DIR.
    # Otherwise, process only the user-supplied version.
    prev_versions_to_include_list = []
    dev_versions_to_include_list = []
    if fim_version != "all" and pfiles is False:
        if config == 'PREV':  # official fim model results
            prev_versions_to_include_list = [fim_version]
        elif config == 'DEV':  # development fim model results
            dev_versions_to_include_list = [fim_version]
    else:
        prev_versions_to_include_list = os.listdir(PREVIOUS_FIM_DIR)
        if config == 'DEV':  # development fim model results
            dev_versions_to_include_list = [fim_version]

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

    # Make sure cycle-previous-files and a previous metric CSV have not been concurrently selected
    if prev_metrics_csv is not None and pfiles is True:
        print(
            "Error: Cycle previous files and previous metric CSV functionality cannot be used concurrently."
        )
        sys.exit(1)

    # Check whether a previous metrics CSV has been provided and, if so, make sure the CSV exists
    if prev_metrics_csv is not None:
        if not os.path.exists(prev_metrics_csv):
            print(f"Error: File does not exist at {prev_metrics_csv}")
            sys.exit(1)
        else:
            print(f"Metrics will be combined with previous metric CSV: {prev_metrics_csv}")
            print()
    else:
        print("ALERT: A previous metric CSV has not been provided (-pcsv) - this is optional.")
        print()

    # Print whether the previous files will be cycled through
    if pfiles is True:
        print("ALERT: Metrics from previous directories will be compiled.")
        print()
    else:
        print(
            "ALERT: Metrics from previous directories will NOT be compiled (-pfiles not provided) \n"
            "   - pfiles is optional -"
        )
        print()

    # Set up multiprocessor
    with ProcessPoolExecutor(max_workers=job_number_huc) as executor:
        # Loop through all test cases, build the alpha test arguments, and submit them to the process pool
        executor_dict = {}

        for test_case_class in all_test_cases:
            if not os.path.exists(test_case_class.fim_dir):
                continue

            fh.vprint(f"test_case_class.test_id is {test_case_class.test_id}", verbose)

            alpha_test_args = {
                'calibrated': calibrated,
                'model': model,
                'mask_type': 'huc',
                'overwrite': overwrite,
                'verbose': gms_verbose if model == 'GMS' else verbose,
                'gms_workers': job_number_branch,
            }

            try:
                future = executor.submit(test_case_class.alpha_test, **alpha_test_args)
                executor_dict[future] = test_case_class.test_id
            except Exception as ex:
                print(f"*** {ex}")
                traceback.print_exc()
                sys.exit(1)

        # Send the executor to the progress bar and wait for all MS tasks to finish
        progress_bar_handler(
            executor_dict, True, f"Running {model} alpha test cases with {job_number_huc} workers"
        )
        # wait(executor_dict.keys())

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

    ## if using DEV version, include the testing versions the user included with the "-dc" flag
    if dev_versions_to_compare is not None:
        dev_versions_to_include_list += dev_versions_to_compare

    # Specify which results to iterate through
    if config == 'DEV':
        iteration_list = [
            'official',
            'testing',
        ]  # iterating through official model results AND testing model(s)
    else:
        iteration_list = ['official']  # only iterating through official model results

    print("================================")
    print("End synthesize test cases")

    end_time = datetime.now()
    dt_string = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    print(f"ended: {dt_string}")

    # Calculate duration
    time_duration = end_time - start_time
    print(f"Duration: {str(time_duration).split('.')[0]}")
    print()
