import os
import argparse
import geopandas as gpd
import xarray as xr
import fsspec
import pandas as pd
from datetime import datetime
from typing import List, Tuple

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

def gen_retro_fim(hydrofabric_dir: str, fim_version: str, huc: str, date_range: Tuple[str, str]) -> None:
    # Find FIM version directory
    fim_version_dir = find_fim_version_dir(hydrofabric_dir, fim_version)
    
    # Check if HUC exists
    check_huc_exists(fim_version_dir, huc)
    
    # Load NWM flows and HUC8 geodataframes
    nwm_flows = gpd.read_file("nwm_flows.gpkg")
    huc8_gdf = gpd.read_file("path_to_huc8.gpkg", layer="HUC8")
    
    # Get feature IDs in the specified HUC8
    feature_ids = get_feature_ids_in_huc8(nwm_flows, huc8_gdf[huc8_gdf['HUC8'] == huc])
    
    # Open AWS Zarr archive
    ds = open_ds("https://noaa-nwm-retrospective-2-1-pds.s3.amazonaws.com/model_output")
    
    # Parse date range
    start_time, end_time = [datetime.strptime(d, "%Y-%m-%d") for d in date_range]
    
    # Get peak discharge time
    peak_time = get_peak_discharge_time(ds, feature_ids, start_time, end_time)
    
    # Create flowfile
    flowfile = create_flowfile(ds, feature_ids, peak_time)
    
    # Save flowfile
    flowfile_path = os.path.join(fim_version_dir, huc, f"{huc}_flowfile.csv")
    flowfile.to_csv(flowfile_path, index=False)
    
    produce_mosaicked_inundation(
        hydrofabric_dir=fim_version_dir,
        hucs=[huc],
        flow_file=flowfile_path,
        inundation_raster=os.path.join(fim_version_dir, huc, f"{huc}_inundation.tif"),
        inundation_polygon=os.path.join(fim_version_dir, huc, f"{huc}_inundation.gpkg"),
        depths_raster=os.path.join(fim_version_dir, huc, f"{huc}_depths.tif")
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate retrospective FIM")
    parser.add_argument("--fim-version", required=True, help="FIM version")
    parser.add_argument("--huc", required=True, help="HUC code")
    parser.add_argument("--date-range", required=True, nargs=2, help="Date range (start end)")
    parser.add_argument("--hydrofabric-dir", required=True, help="Path to hydrofabric directory")
    
    args = parser.parse_args()
    
    gen_retro_fim(args.hydrofabric_dir, args.fim_version, args.huc, args.date_range)
