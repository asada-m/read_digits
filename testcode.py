# -*- coding: utf-8 -*-
import os
import math
import datetime
from dataclasses import dataclass, field
import statistics

import numpy as np
import cv2

IMAGE_EXTENSIONS = ('.png','.jpg','.PNG','.JPG')
DIGITS_LOOKUP = {
    (1, 1, 1, 0, 1, 1, 1): '0',
    (0, 0, 1, 0, 0, 1, 0): '1',
    (1, 0, 1, 1, 1, 0, 1): '2',
    (1, 0, 1, 1, 0, 1, 1): '3',
    (0, 1, 1, 1, 0, 1, 0): '4',
    (1, 1, 0, 1, 0, 1, 1): '5',
    (1, 1, 0, 1, 1, 1, 1): '6',
    (1, 0, 1, 0, 0, 1, 0): '7',
    (1, 1, 1, 0, 0, 1, 0): '7',
    (1, 1, 1, 1, 1, 1, 1): '8',
    (1, 1, 1, 1, 0, 1, 1): '9',
    (1, 1, 1, 1, 0, 1, 0): '9',
    (0, 0, 0, 1, 0, 0, 0): '-',}
"""
Order of 7 segments:
   -- 0 --   
  |       |  
  1       2  
  |       |  
   -- 3 --   
  |       |  
  4       5  
  |       |  
   -- 6 --   

#=============================================
# Frame coordinates of a Image:
# (ULw, ULh) --- (URw, URh)       Upper-Left / Upper-Right
#     |              |
# (LLw, LLh) --- (LRw, LRh)       Lower-Left / Lower-Right
#
# Axis of Image shown in Matplotlib
# (0,0) ---> (w,0) width direction (= 2nd axis in numpy)
#   |
#   v
# (0,h) height direction (= 1st axis in numpy)
#
# example: width 400 & height 300
# Frame dictionary = {ULw:0,ULh:0,URw:400,URh:0,LLw:0,LLh:300,LRw:400,LRh:300}
#=============================================
"""


FRAME_NAMELIST = ('UL','UR','LL','LR')
FRAME_NAMELIST_each = ('ULw','ULh','URw','URh','LLw','LLh','LRw','LRh')
CALC_FRAMES = ('UL','UR','LR','LL')


class ReadDigits:
    pass



# this is a branch and marging test.

