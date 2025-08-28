#!/usr/bin/env python3


import argparse
import os
import pathlib
from glob import glob
from logging import exception



def __read_included_files(parent_dir_path, huc_level):
    """
    Reads the list of HUCs that are included in the analysis
    """
    included_huc_list = f'included_huc{huc_level}_withAlaska.lst'
    filename_pattern = os.path.join(parent_dir_path, included_huc_list)

    with open(filename_pattern, 'r') as f:
        accepted_hucs_set = {fl.rstrip() for fl in f.readlines()}

    return accepted_hucs_set


def __read_input_hucs(hucs):
    huc_list = set()
    if os.path.isfile(hucs[0]):
        source_file_extension = pathlib.Path(hucs[0]).suffix

        if source_file_extension.lower() != ".lst":
            raise Exception("Incoming file must be in .lst format if submitting a file name and path.")

        with open(hucs[0], 'r') as hucs_file:
            file_lines = hucs_file.readlines()
            f_list = [__clean_huc_value(fl) for fl in file_lines]
            huc_list.update(f_list)
    else:
        if len(hucs) > 0:
            for huc in hucs:
                huc_list.add(__clean_huc_value(huc))
        else:
            huc_list.add(__clean_huc_value(hucs[0]))

    return huc_list


def __clean_huc_value(huc):
    # Strips the newline character plus
    # single or double quotes (which sometimes happens)
    huc = huc.strip().replace("\"", "")
    huc = huc.replace("\'", "")
    return huc


def __check_for_membership(hucs, accepted_hucs_set):
    for huc in hucs:
        if (type(huc) is str) and (not huc.isnumeric()):
            msg = f"Huc value of {huc} does not appear to be a number. "
            msg += "It could be an incorrect value but also could be that the huc list "
            msg += "(if you used one), is not unix encoded."
            raise KeyError(msg)

        if huc not in accepted_hucs_set:
            msg = f"HUC {huc} not found in available inputs. Edit HUC inputs or acquire datasets & try again."
            raise KeyError(msg)


def check_hucs(hucs, inputsDir):

    def get_huc_level(hucs: set):
        """
        Returns the length of the HUCs in the set
        """
        huc_lens = {len(huc) for huc in hucs}
        if len(huc_lens) != 1:
            raise ValueError("All HUCs must be the same length")
        
        return huc_lens.pop()

    list_hucs = __read_input_hucs(hucs)

    list_hucs_level = get_huc_level(list_hucs)

    huc_list_path = os.path.join(inputsDir, 'huc_lists')
    accepted_hucs = __read_included_files(huc_list_path, list_hucs_level)
    
    accepted_hucs_level = get_huc_level(accepted_hucs)


    if accepted_hucs_level != list_hucs_level:
        raise ValueError(
            f"Accepted HUCs and input HUCs are not the same level, {accepted_hucs_level} and {list_hucs_level} respectively"
        )

    __check_for_membership(list_hucs, accepted_hucs)

    # we need to return the number of hucs being used.
    # it is not easy to return a value to bash, except with standard out.
    # so we will just to a print line back (Note: This means there can be no other
    # print commands in this file, even for debugging, as bash will pick up the
    # very first "print"
    print(len(list_hucs))


if __name__ == '__main__':
    # parse arguments
    parser = argparse.ArgumentParser(description='Checks input hucs for availability within inputs')
    parser.add_argument(
        '-u',
        '--hucs',
        help='Line-delimited file or list of HUCs to check availibility for',
        required=True,
        nargs='+',
    )
    parser.add_argument('-i', '--inputsDir', help='Inputs directory', required=True)

    # extract to dictionary
    args = vars(parser.parse_args())

    # call function
    check_hucs(**args)
