"""
Manage Hydrologic Unit Codes
"""
from __future__ import annotations
from typing import Set

import warnings
import os

import geopandas as gpd
import pandas as pd
from dotenv import load_dotenv

try:
    import pygeohydro as gh
except ImportError:
    pygeohydro_installed = False
    pass
else:
    pygeohydro_installed = True

# Load environment variables
src_dir = os.getenv('srcDir')
load_dotenv(f'{src_dir}/bash_variables.env')
input_WBD = os.getenv('input_WBD_gdb')

class Huc:
    """
    Manage Hydrologic Unit Codes

    Parameters
    ----------
    huc : str
        The Hydrologic Unit Code (HUC) to manage

    Attributes
    ----------
    huc : str
        The Hydrologic Unit Code (HUC) to manage
    huc_level : int
        The level of the HUC

    Methods
    -------
    get_child_hucs(huc_level: int) -> Set of str
        Get the child HUCs for a given HUC level
    get_parent_hucs(huc_level: int) -> Set of str
        Get the parent HUCs for a given HUC level
    is_valid -> bool
        Check if the HUC is valid
    """

    _valid_wbd_sources = {'pygeohydro', 'local'}
    _valid_huc_levels = {2, 4, 6, 8, 10, 12, 14, 16}

    def __init__(self, huc: str, wbd_source: str = 'local'):

        self.huc = huc
        self.huc_level = len(huc)
        self._available_hucs = {}
        self._child_hucs = {}
        self._parent_hucs = {}
        self._wbd_source = wbd_source

        if self.huc_level not in self._valid_huc_levels:
            raise ValueError(f'{self.huc_level} is not a valid HUC level. Choose from {self._valid_huc_levels}')
        
        if self._wbd_source not in self._valid_wbd_sources:
            raise ValueError(f'{wbd_source} is not a valid WBD source. Choose from {self._valid_wbd_sources}')
        
        if (not pygeohydro_installed) and (self._wbd_source == 'pygeohydro'):
            warnings.warn('pygeohydro is not installed. Using local WBD data instead.')
            self._wbd_source = 'local'

    def _get_huc_pygh(self, huc_level: int) -> Set[str]:
        """
        Get the HUC set for a given HUC level
        """
        if huc_level not in self._valid_huc_levels:
            raise ValueError(f'{huc_level} is not a valid HUC level. Choose from {self._valid_huc_levels}')
        
        # Get the HUCs for the given HUC level
        hucs = gh.watershed.huc_wb_full(huc_level)[f'huc{huc_level}']
        
        # Convert the HUCs to a set
        if not isinstance(hucs, pd.Series):
            hucs = hucs.iloc[:, 0]

        return set(hucs.to_list())
    
    def _get_huc_local(self, huc_level: int) -> Set[str]:
        """
        Get the HUC set for a given HUC level
        """
        if huc_level not in self._valid_huc_levels:
            raise ValueError(f'{huc_level} is not a valid HUC level. Choose from {self._valid_huc_levels}')
        
        # TODO: This is a temporary fix. Need to remove this hardcoding
        input_WBD = '/data/inputs/wbd/WBD_National_EPSG_5070_clip_dem_domain.gpkg'

        # Get the HUCs for the given HUC level
        hucs = gpd.read_file(input_WBD, layer=f'WBDHU{huc_level}')
        
        return set(hucs[f'HUC{huc_level}'])

    def _get_huc(self, huc_level: int) -> Set[str]:
        """
        Get the HUC set for a given HUC level
        """
        if self._wbd_source == 'pygeohydro':
            return self._get_huc_pygh(huc_level)
        elif self._wbd_source == 'local':
            return self._get_huc_local(huc_level)

    def _set_available_hucs(self, huc_level: int):
        """Set the child HUCs for a given HUC level"""
        if huc_level not in self._available_hucs:
            self._available_hucs[huc_level] = self._get_huc(huc_level)

    def get_child_hucs(self, huc_level: int) -> Set[str]:
        """Get the child HUCs for a given HUC level"""
        self._set_available_hucs(huc_level)
        if huc_level not in self._child_hucs:
            self._child_hucs[huc_level] = {h for h in self._available_hucs[huc_level] if h[:self.huc_level] == self.huc}
        return self._child_hucs[huc_level]
    
    def get_parent_hucs(self, huc_level: int) -> Set[str]:
        """Get the parent HUCs for a given HUC level"""
        self._set_available_hucs(huc_level)
        if huc_level not in self._parent_hucs:
            self._parent_hucs[huc_level] = {h for h in self._available_hucs[huc_level] if h == self.huc[:huc_level]}
        return self._parent_hucs[huc_level]
    
    @property
    def is_valid(self) -> bool:
        """Check if the HUC is valid"""
        self._set_available_hucs(self.huc_level)
        return self.huc in self._available_hucs[self.huc_level]
    
    def __str__(self):
        return self.huc
    
    def __repr__(self):
        return self.huc
    
    def __eq__(self, other: Huc):
        return self.huc == other.huc
    
    def __lt__(self, other: Huc):
        return self.huc < other.huc
    
    def __le__(self, other: Huc):
        return self.huc <= other.huc
    
    def __gt__(self, other: Huc):
        return self.huc > other.huc
    
    def __ge__(self, other: Huc):
        return self.huc >= other.huc
    
    def __ne__(self, other: Huc):
        return self.huc != other.huc
    
    def __hash__(self):
        return hash(self.huc)
    
    def __contains__(self, other: Huc):
        return other.huc.startswith(self.huc)
    
    def __len__(self):
        return len(self.huc)
    
    def __getitem__(self, key: int):
        return self.huc[key]
    
    def __iter__(self):
        return iter(self.huc)
    
    def __reversed__(self):
        return reversed(self.huc)
    
    def __add__(self, other: Huc):
        return Huc(self.huc + other.huc)
    
    def __sub__(self, other: Huc):
        return Huc(self.huc[:-len(other.huc)])
    
    def __truediv__(self, other: Huc):
        return Huc(self.huc[:-len(other.huc)])
    
    def __floordiv__(self, other: Huc):
        return Huc(self.huc[:-len(other.huc)])
    
    def __mod__(self, other: Huc):
        return Huc(self.huc[:-len(other.huc)])
    
    def __mul__(self, other: int):
        return Huc(self.huc * other)
    
    def __rmul__(self, other: int):
        return Huc(self.huc * other)


if __name__ == '__main__':

    huc = Huc('01010001')
    print(f'Getting child HUC12s for {huc}')
    print(huc.get_child_hucs(12))

    print(f'Getting parent HUC2s for {huc}')
    print(huc.get_parent_hucs(6))

    hucs = [
        Huc('01010002'),
        Huc('0202'),
        Huc('120902'),
    ]

    print("Multiple HUCs")
    for huc in hucs:
        print(f'{huc} is valid: {huc.is_valid}')
        print(f'{huc} has children HUC10s: {huc.get_child_hucs(10)}')