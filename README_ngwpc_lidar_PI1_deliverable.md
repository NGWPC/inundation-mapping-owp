# NGWPC PI-1 Deliverable

Generally speaking this code deliverable contains the code to acquire, produce HAND with, optimize and evaluate HAND based FIMs. 

The following contains a list of files that were updated from the latest commit (`e7a6b7956`) of `noaa-owp/inundation-mapping:dev`. 

## Added or Modified Files
1. `.gitignore`
    - Updated to account for possibility of having a `cache/` artifact.
2. `Dockerfile`
    - Updated with some comments on Pipfile and Pipfile.lock updating.
3. `Pipfile`
    - New dependencies added.
4. `Pipfile.lock`
    - Updated accordingly.
5. `config/params_template.env`
    - Updated for DEM selection and resolution.
6. `data/usgs/acquire_and_preprocess_3dep_dems.py`
    - Update to executable mode.
7. `data/usgs/create_3dep_tile_index.py`
    - Creates tile indices for 1 and 3m 3DEP tiles.
8. `data/usgs/get_3dep_static_tiles.py`
    - Retrieves and processes 1 and 3m in tile index(ices) passed. Makes a VRT of tiles with existing 10m seamless VRT.
9. `data/wbd/generate_pre_clip_fim_huc8.py`
    - Updated logic for input dem selection.
10. `src/agreedem.py`
    - Updated for bigtiff reading.
11. `src/bash_variables.env`
    - Updated for additional seamless DEM source.
12. `src/run_unit_wb.sh`
    - Updated for seamless DEM and resolution selection.
13. `tools/acquire_tigerweb_data.py`
    - Acquires Tigerweb urban/city census areas.
14. `tools/convert_city_names_to_huc8s.py`
    - Selects HUC8's based on names.
15. `tools/run_test_case.py`
    - Updated to optimize for peak memory and garbage collection.
16. `tools/tools_shared_functions.py`
    - Updated to optimize for peak memory and garbage collection.
```