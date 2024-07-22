
def create_master_metrics_csv(
    master_metrics_csv_output,
    dev_versions_to_include_list,
    prev_versions_to_include_list,
    iteration_list,
    pfiles,
    prev_metrics_csv,
):
    """
    This function searches for and collates metrics into a single CSV file that can queried database-style.
        The CSV is an input to eval_plots.py.
        This function automatically looks for metrics produced for official versions and loads them into
            memory to be written to the output CSV.

    Args:
        master_metrics_csv_output (str)    : Full path to CSV output.
                                                If a file already exists at this path, it will be overwritten.
        dev_versions_to_include_list (list): A list of non-official FIM version names.
                                                If a user supplied information on the command line using the
                                                -dc flag, then this function will search for metrics in the
                                                "testing_versions" library of metrics and include them in
                                                the CSV output.
    """

    # Construct header
    metrics_to_write = [
        'true_negatives_count',
        'false_negatives_count',
        'true_positives_count',
        'false_positives_count',
        'contingency_tot_count',
        'cell_area_m2',
        'TP_area_km2',
        'FP_area_km2',
        'TN_area_km2',
        'FN_area_km2',
        'contingency_tot_area_km2',
        'predPositive_area_km2',
        'predNegative_area_km2',
        'obsPositive_area_km2',
        'obsNegative_area_km2',
        'positiveDiff_area_km2',
        'CSI',
        'FAR',
        'TPR',
        'TNR',
        'PND',
        'PPV',
        'NPV',
        'ACC',
        'Bal_ACC',
        'MCC',
        'EQUITABLE_THREAT_SCORE',
        'PREVALENCE',
        'BIAS',
        'F1_SCORE',
        'TP_perc',
        'FP_perc',
        'TN_perc',
        'FN_perc',
        'predPositive_perc',
        'predNegative_perc',
        'obsPositive_perc',
        'obsNegative_perc',
        'positiveDiff_perc',
        'masked_count',
        'masked_perc',
        'masked_area_km2',
    ]

    # Create table header
    additional_header_info_prefix = ['version', 'nws_lid', 'magnitude', 'huc']
    list_to_write = [
        additional_header_info_prefix
        + metrics_to_write
        + ['full_json_path']
        + ['flow']
        + ['benchmark_source']
        + ['extent_config']
        + ["calibrated"]
    ]

    # add in composite of versions (used for previous FIM3 versions)
    if "official" in iteration_list:
        composite_versions = [v.replace('_ms', '_comp') for v in prev_versions_to_include_list if '_ms' in v]
        prev_versions_to_include_list += composite_versions

    # Iterate through 5 benchmark sources
    for benchmark_source in ['ble', 'nws', 'usgs', 'ifc', 'ras2fim']:
        benchmark_test_case_dir = os.path.join(TEST_CASES_DIR, benchmark_source + '_test_cases')
        test_cases_list = [d for d in os.listdir(benchmark_test_case_dir) if re.match(r'\d{8}_\w{3,7}', d)]

        if benchmark_source in ['ble', 'ifc', 'ras2fim']:
            magnitude_list = MAGNITUDE_DICT[benchmark_source]

            # Iterate through available test cases
            for each_test_case in test_cases_list:
                try:
                    # Get HUC id
                    int(each_test_case.split('_')[0])
                    huc = each_test_case.split('_')[0]

                    # Update filepaths based on whether the official or dev versions should be included
                    for iteration in iteration_list:
                        if (
                            iteration == "official"
                        ):  # and str(pfiles) == "True": # "official" refers to previous finalized model versions
                            versions_to_crawl = os.path.join(
                                benchmark_test_case_dir, each_test_case, 'official_versions'
                            )
                            versions_to_aggregate = prev_versions_to_include_list

                        if (
                            iteration == "testing"
                        ):  # "testing" refers to the development model version(s) being evaluated
                            versions_to_crawl = os.path.join(
                                benchmark_test_case_dir, each_test_case, 'testing_versions'
                            )
                            versions_to_aggregate = dev_versions_to_include_list

                        # Pull version info from filepath
                        for magnitude in magnitude_list:
                            for version in versions_to_aggregate:
                                if '_ms' in version:
                                    extent_config = 'MS'
                                elif ('_fr' in version) or (version == 'fim_2_3_3'):
                                    extent_config = 'FR'
                                else:
                                    extent_config = 'COMP'
                                if "_c" in version and version.split('_c')[1] == "":
                                    calibrated = "yes"
                                else:
                                    calibrated = "no"
                                version_dir = os.path.join(versions_to_crawl, version)
                                magnitude_dir = os.path.join(version_dir, magnitude)

                                # Add metrics from file to metrics table ('list_to_write')
                                if os.path.exists(magnitude_dir):
                                    magnitude_dir_list = os.listdir(magnitude_dir)
                                    for f in magnitude_dir_list:
                                        if '.json' in f:
                                            flow = 'NA'
                                            nws_lid = "NA"
                                            sub_list_to_append = [version, nws_lid, magnitude, huc]
                                            full_json_path = os.path.join(magnitude_dir, f)
                                            if os.path.exists(full_json_path):
                                                stats_dict = json.load(open(full_json_path))
                                                for metric in metrics_to_write:
                                                    sub_list_to_append.append(stats_dict[metric])
                                                sub_list_to_append.append(full_json_path)
                                                sub_list_to_append.append(flow)
                                                sub_list_to_append.append(benchmark_source)
                                                sub_list_to_append.append(extent_config)
                                                sub_list_to_append.append(calibrated)

                                                list_to_write.append(sub_list_to_append)
                except ValueError:
                    pass

        # Iterate through AHPS benchmark data
        if benchmark_source in AHPS_BENCHMARK_CATEGORIES:
            test_cases_list = os.listdir(benchmark_test_case_dir)

            for each_test_case in test_cases_list:
                try:
                    # Get HUC id
                    int(each_test_case.split('_')[0])
                    huc = each_test_case.split('_')[0]

                    # Update filepaths based on whether the official or dev versions should be included
                    for iteration in iteration_list:
                        if iteration == "official":  # "official" refers to previous finalized model versions
                            versions_to_crawl = os.path.join(
                                benchmark_test_case_dir, each_test_case, 'official_versions'
                            )
                            versions_to_aggregate = prev_versions_to_include_list

                        if (
                            iteration == "testing"
                        ):  # "testing" refers to the development model version(s) being evaluated
                            versions_to_crawl = os.path.join(
                                benchmark_test_case_dir, each_test_case, 'testing_versions'
                            )
                            versions_to_aggregate = dev_versions_to_include_list

                        # Pull model info from filepath
                        for magnitude in ['action', 'minor', 'moderate', 'major']:
                            for version in versions_to_aggregate:
                                if '_ms' in version:
                                    extent_config = 'MS'
                                elif ('_fr' in version) or (version == 'fim_2_3_3'):
                                    extent_config = 'FR'
                                else:
                                    extent_config = 'COMP'
                                if "_c" in version and version.split('_c')[1] == "":
                                    calibrated = "yes"
                                else:
                                    calibrated = "no"

                                version_dir = os.path.join(versions_to_crawl, version)
                                magnitude_dir = os.path.join(version_dir, magnitude)

                                if os.path.exists(magnitude_dir):
                                    magnitude_dir_list = os.listdir(magnitude_dir)
                                    for f in magnitude_dir_list:
                                        if '.json' in f and 'total_area' not in f:
                                            nws_lid = f[:5]
                                            sub_list_to_append = [version, nws_lid, magnitude, huc]
                                            full_json_path = os.path.join(magnitude_dir, f)
                                            flow = ''
                                            if os.path.exists(full_json_path):
                                                # Get flow used to map
                                                flow_file = os.path.join(
                                                    benchmark_test_case_dir,
                                                    'validation_data_' + benchmark_source,
                                                    huc,
                                                    nws_lid,
                                                    magnitude,
                                                    'ahps_'
                                                    + nws_lid
                                                    + '_huc_'
                                                    + huc
                                                    + '_flows_'
                                                    + magnitude
                                                    + '.csv',
                                                )
                                                if os.path.exists(flow_file):
                                                    with open(flow_file, newline='') as csv_file:
                                                        reader = csv.reader(csv_file)
                                                        next(reader)
                                                        for row in reader:
                                                            flow = row[1]

                                                # Add metrics from file to metrics table ('list_to_write')
                                                stats_dict = json.load(open(full_json_path))
                                                for metric in metrics_to_write:
                                                    sub_list_to_append.append(stats_dict[metric])
                                                sub_list_to_append.append(full_json_path)
                                                sub_list_to_append.append(flow)
                                                sub_list_to_append.append(benchmark_source)
                                                sub_list_to_append.append(extent_config)
                                                sub_list_to_append.append(calibrated)
                                                list_to_write.append(sub_list_to_append)
                except ValueError:
                    pass

    # If previous metrics are provided: read in previously compiled metrics and join to calcaulated metrics
    if prev_metrics_csv is not None:
        prev_metrics_df = pd.read_csv(prev_metrics_csv)

        # Put calculated metrics into a dataframe and set the headers
        df_to_write_calc = pd.DataFrame(list_to_write)
        df_to_write_calc.columns = df_to_write_calc.iloc[0]
        df_to_write_calc = df_to_write_calc[1:]

        # Join the calculated metrics and the previous metrics dataframe
        df_to_write = pd.concat([df_to_write_calc, prev_metrics_df], axis=0)

    else:
        df_to_write = pd.DataFrame(list_to_write)
        df_to_write.columns = df_to_write.iloc[0]
        df_to_write = df_to_write[1:]

    # Save aggregated compiled metrics ('df_to_write') as a CSV
    df_to_write.to_csv(master_metrics_csv_output, index=False)

# # example call to create_master_metrics_csv function
# # Note: This function is not compatible with GMS
# create_master_metrics_csv(
#     master_metrics_csv_output=master_metrics_csv,
#     dev_versions_to_include_list=dev_versions_to_include_list,
#     prev_versions_to_include_list=prev_versions_to_include_list,
#     iteration_list=iteration_list,
#     pfiles=pfiles,
#     prev_metrics_csv=prev_metrics_csv,
# )

