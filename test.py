from pathlib import Path
from readdigits import *


def testimshow(im):
    fig,ax = plt.subplots()
    ax.imshow(im,cmap='gray')
    plt.show()



d = Path('../RecDigits/iroiro/TMP_hicube_eco')
print(d.exists())
filelist = [p for p in d.glob('*.jpg')]

fn = filelist[0].resolve().as_posix()

im = cv2.imread(fn,0)
#caruco = Corners._from_aruco_markers(im, [0,1,2,3])
# 前処理
im2 = trim_aruco_markers(im, [0,1,2,3])

# 切り取り座標指定
# abs --> ratio 換算したい
# gui 版は全部 ratio でもよいかもしれない
corners = Corners(30,88,210,88,2,219,182,219)
disp = Display(position_type='abs',corners=corners)
im3 = disp.trim(im2)


testimshow(im3)

