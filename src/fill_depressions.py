#!/usr/bin/env python3
import argparse
import os

import numpy as np
import rasterio
import whitebox
import pyflwdir

def fill_depressions(workspace, branch_zero_id):
    '''
    Wrapper around either whitebox tool fill_depressions methods:
    https://www.whiteboxgeo.com/manual/wbt_book/available_tools/hydrological_analysis.html#filldepressions
    '''
    
    # Set wbt envs
    wbt = whitebox.WhiteboxTools()
    wbt.set_verbose_mode(True)

    if branch_zero_id:
        input_dem = os.path.join(workspace, f'dem_burned_{branch_zero_id}.tif')
        output_dem = os.path.join(workspace, f'dem_burned_filled_{branch_zero_id}.tif')
    else:
        input_dem = os.path.join(workspace, f'dem_burned.tif')
        output_dem = os.path.join(workspace, f'dem_burned_filled.tif')

    wbt.fill_depressions(
        input_dem,
        output_dem,
        fix_flats=False, 
        flat_increment=None, 
        max_depth=None
    )

def fill_depressions_pyflwdir(workspace, branch_zero_id):
    '''
    Pit Fill method wrapper for pyflwdir methods:
    https://deltares.github.io/pyflwdir/latest/_generated/pyflwdir.dem.fill_depressions.html#pyflwdir-dem-fill-depressions
    '''
    
    if branch_zero_id:
        input_dem = os.path.join(workspace, f'dem_burned_{branch_zero_id}.tif')
        output_dem = os.path.join(workspace, f'dem_burned_filled_{branch_zero_id}.tif')
    else:
        input_dem = os.path.join(workspace, f'dem_burned.tif')
        output_dem = os.path.join(workspace, f'dem_burned_filled.tif')

    # Example:
    # pyflwdir.dem.fill_depressions(elevtn,
    #     outlets='edge',
    #     idxs_pit=None,
    #     nodata=-9999.0,
    #     max_depth=-1.0,
    #     elv_max=None,
    #     connectivity=8
    # )



if __name__ == '__main__':
    # Parse arguments
    parser = argparse.ArgumentParser(description='Fill depressions')
    parser.add_argument('-w', '--workspace', help='Workspace', required=True)
    parser.add_argument('-b', '--branch_zero_id', help='If branch_zero_id is provided, update output path', required=False, default=None)

    # Extract to dictionary and assign to variables.
    args = vars(parser.parse_args())

    # rename variable inputs
    workspace = args['workspace']
    branch_zero_id = args['branch_zero_id']

    # Run pyflwdir fill_depressions
    # fill_depressions_pyflwdir(
    #     workspace,
    #     branch_zero_id
    # )
    
    # Run WBT fill_depressions
    fill_depressions(
        workspace,
        branch_zero_id
    )
