from pathlib import Path
from readdigits import Trimming

dir = Path('./RecDigits/iroiro/TMP_hicube_eco')
filelist = [p for p in dir.glob('*.jpg')]

fn = filelist[0]

t = Trimming()


