"""
Utility functions for CAD parsing.
Python 3 port of onshape-cad-parser/utils.py
"""

import math
from collections import OrderedDict


def xyz_list2dict(l):
    return OrderedDict({'x': l[0], 'y': l[1], 'z': l[2]})


def angle_from_vector_to_x(vec):
    """Compute angle from a 2D vector to the positive x-axis, in [0, 2π)."""
    angle = 0.0
    # Quadrant layout:
    # 2 | 1
    # -----
    # 3 | 4
    if vec[0] >= 0:
        if vec[1] >= 0:
            angle = math.asin(vec[1])       # Q1
        else:
            angle = 2.0 * math.pi - math.asin(-vec[1])  # Q4
    else:
        if vec[1] >= 0:
            angle = math.pi - math.asin(vec[1])         # Q2
        else:
            angle = math.pi + math.asin(-vec[1])         # Q3
    return angle
