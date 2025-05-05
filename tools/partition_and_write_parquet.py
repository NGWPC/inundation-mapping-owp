#!/usr/bin/env python3
import argparse
import pandas as pd
import os

def partition_and_write_parquet(input_file, output_dir, column_name, value):
    """
    Check if a value exists in a Parquet file column and extract matching rows.
    
    Inputs:
        input_file (str): Path to input Parquet file
        ouput_dir (str): Path to output Parquet file
        column_name (str): Name of column to check
        value: Value to search for
    
    Outputs:
        New parquet file with all matching rows in the <output_dir>/<value> directory.
    """
    try:
        matching_data = pd.read_parquet(
            input_file,
            filters=[(column_name, "=", value)]
        )

        huc_output_dir = os.path.join(output_dir, value)
        output_file = os.path.join(huc_output_dir, "ripple1d_rating_curve.parquet")

        if not matching_data.empty:
            if os.path.isdir(huc_output_dir) is False:
                os.mkdir(huc_output_dir)
                print(f"Created directory: {output_dir}, .parquet files will be written there.")
            elif os.path.isdir(huc_output_dir) is True:
               print(f"Output Directory: {huc_output_dir} exists, .parquet files will be written there.")
        
            # Write to new Parquet file
            matching_data.to_parquet(output_file, index=False)
        else:
            print(f"Value: {value} was not found in the column {column_name}")
            print(f"No file was written.")
                  
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return False
    

if __name__ == '__main__':
    '''
    python3 partition_and_write_parquet.py -i ~/projects/hand_fim/inputs/rating_curve/ripple1d/12090301/ripple1d_rating_curve_table_mip.parquet \
        -o ~/projects/hand_fim/inputs/rating_curve/ripple1d/test \
        -c "huc8" \
        -v "12090301"
    '''
    parser = argparse.ArgumentParser(
        description='Filters and writes a new .parquet file for a column name a value.'
    )
    parser.add_argument('-i', '--input_file', help='Input parquet file.', required=True)
    parser.add_argument(
        '-o',
        '--output_dir',
        help='Output parquet file with filtered rows.',
        required=True,
    )
    parser.add_argument('-c', '--column_name',help='Column name to filter', required=True, type=str)
    parser.add_argument('-v', '--value',help='Value to filter', required=True, type=str)

    # Extract to dictionary and assign to variables.
    args = vars(parser.parse_args())

    partition_and_write_parquet(**args)
