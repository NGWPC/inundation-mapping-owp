import os
import pdb
import argparse
import geopandas as gpd
import xarray as xr
import fsspec
import pandas as pd
from datetime import datetime
from typing import List, Tuple

from tools_shared_variables import OUTPUTS_DIR, INPUTS_DIR, WORK_DIR
from inundate_mosaic_wrapper import produce_mosaicked_inundation

def open_ds(url: str) -> xr.DataArray:
    return xr.open_zarr(
        fsspec.get_mapper(url, anon=True), consolidated=True, mask_and_scale=True
    )['streamflow'].drop_vars(['latitude', 'elevation', 'gage_id', 'longitude', 'order'])

def get_feature_ids_in_huc8(nwm_flows: gpd.GeoDataFrame, huc8_gdf: gpd.GeoDataFrame) -> List[int]:
    return sorted(nwm_flows[nwm_flows.intersects(huc8_gdf.unary_union)]['ID'].tolist())

def get_peak_discharge_time(ds: xr.DataArray, feature_ids: List[int], start_time: datetime, end_time: datetime) -> datetime:
    ts = ds.sel(feature_id=feature_ids, time=slice(start_time, end_time))
    peak_times = ts.idxmax(dim='time')
    peak_times_series = peak_times.to_series()
    mode_result = peak_times_series.mode()
    
    if mode_result.empty:
        modal_peak_time = peak_times_series.median()
    else:
        modal_peak_time = mode_result.iloc[0]
    
    return pd.Timestamp(modal_peak_time)

def create_flowfile(ds: xr.DataArray, feature_ids: List[int], peak_time: datetime) -> pd.DataFrame:
    df = ds.sel(feature_id=feature_ids, time=peak_time, method='nearest').to_dataframe().reset_index()
    return df[['feature_id', 'streamflow']].rename(columns={'streamflow': 'discharge'})

def find_fim_version_dir(hydrofabric_dir: str, fim_version: str) -> str:
    for dir_name in os.listdir(hydrofabric_dir):
        if fim_version in dir_name:
            return os.path.join(hydrofabric_dir, dir_name)
    raise ValueError(f"FIM version '{fim_version}' not found in {hydrofabric_dir}")

def check_huc_exists(fim_version_dir: str, huc: str) -> None:
    if huc not in os.listdir(fim_version_dir):
        raise ValueError(f"HUC '{huc}' not found in {fim_version_dir}")

def gen_retro_fim(hydrofabric_dir: str, fim_version: str, huc: str, date_range: Tuple[str, str], huc8_gdf: gpd.GeoDataFrame, nwm_flows: gpd.GeoDataFrame) -> None:
    # Find FIM version directory
    fim_version_dir = find_fim_version_dir(hydrofabric_dir, fim_version)
    
    # Check if HUC exists
    check_huc_exists(fim_version_dir, huc)
    huc8_subset = huc8_gdf[huc8_gdf['HUC8'] == huc]

    # Get feature IDs in the specified HUC8
    feature_ids = get_feature_ids_in_huc8(nwm_flows, huc8_subset)

    # Open AWS Zarr archive
    url_conus = 's3://noaa-nwm-retrospective-3-0-pds/CONUS/zarr/chrtout.zarr'
    ds = open_ds(url_conus)
    
    # Parse date range
    start_time, end_time = [datetime.strptime(d, "%Y-%m-%d") for d in date_range]
    
    # Get peak discharge time
    peak_time = get_peak_discharge_time(ds, feature_ids, start_time, end_time)
    
    # Create flowfile
    flowfile = create_flowfile(ds, feature_ids, peak_time)
    
    # Save flowfile
    flowfile_path = os.path.join(WORK_DIR, huc, f"{huc}_flowfile.csv")
    os.makedirs(os.path.dirname(flowfile_path), exist_ok=True)
    pdb.set_trace()
    flowfile.to_csv(flowfile_path, index=False)
    
    produce_mosaicked_inundation(
        hydrofabric_dir=fim_version_dir,
        hucs=[huc],
        flow_file=flowfile_path,
        inundation_raster=os.path.join(WORK_DIR, huc, f"{huc}_retro_inundation.tif"),
        mask=huc8_subset
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate retrospective FIM")
    parser.add_argument("--fim-version", required=True, help="FIM version")
    parser.add_argument("--huc", required=True, help="HUC code")
    parser.add_argument("--date-range", required=True, nargs=2, help="Date range (start end)")
    parser.add_argument("--hydrofabric-dir", required=False, default = OUTPUTS_DIR, help="Path to hydrofabric directory")
    parser.add_argument("--huc-shapes", required=False, default = os.path.join(INPUTS_DIR,'wbd','WBD_National.gpkg'), help="Path to huc gpkg")
    parser.add_argument("--flow-feat", required=False, default = os.path.join(INPUTS_DIR,'nwm_hydrofabric',"nwm_flows.gpkg"), help="Path to flow features gpkg")

    # Load NWM flows and HUC8 geodataframes
    args = parser.parse_args()
    huc8_gdf = gpd.read_file(args.huc_shapes, layer="WBDHU8")
    nwm_flows = gpd.read_file(args.flow_feat)
    
    gen_retro_fim(args.hydrofabric_dir, args.fim_version, args.huc, args.date_range, huc8_gdf, nwm_flows)
