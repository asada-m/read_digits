import csv
import math
import statistics
from datetime import datetime as dt
from pathlib import Path
from collections import OrderedDict
from typing import NamedTuple
import numpy as np
import cv2
from cv2 import aruco
import matplotlib.pyplot as plt

version = __version__ = "0.62"

# ======================================================================
# 定数
# ======================================================================
DIGITS_LOOKUP = {
    (1, 1, 1, 0, 1, 1, 1): '0',
    (0, 0, 1, 0, 0, 1, 0): '1',
    (1, 0, 1, 1, 1, 0, 1): '2',
    (1, 0, 1, 1, 0, 1, 1): '3',
    (0, 1, 1, 1, 0, 1, 0): '4',
    (1, 1, 0, 1, 0, 1, 1): '5',
    (0, 1, 0, 1, 1, 1, 1): '6',
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
# Frame corners of a Image in Matplotlib:
# (TLw, TLh) --- (TRw, TRh)       Top-Left / Top-Right
#     |              |
# (BLw, BLh) --- (BRw, BRh)       Bottom-Left / Bottom-Right
#
# Axis of Image shown in Matplotlib
# (0,0) ---> (w,0) width direction (= 2nd axis in numpy&cv2)
#   |
#   v
# (0,h) height direction (= 1st axis in numpy&cv2)
#
# example: width 400 & height 300
# --> Frame dictionary = {TLw:0,TLh:0,TRw:400,TRh:0,BLw:0,BLh:300,BRw:400,BRh:300}
#=============================================
"""
ARUCO_DICT = aruco.getPredefinedDictionary(aruco.DICT_4X4_50) # 4X4のマーカーを50個

# ======================================================================

class Corners(NamedTuple):
    TLw: float
    TLh: float
    TRw: float
    TRh: float
    BLw: float
    BLh: float
    BRw: float
    BRh: float

    @classmethod
    def _from_2corners(cls, TLw, TLh, BRw, BRh):
        """左上・右下の座標のみ使う
        """
        return cls(TLw,TLh,BRw,TLh,TLw,BRh,BRw,BRh)

    @classmethod
    def _from_aruco_markers(cls, img, aruco_ids):
        """画像のarucoマーカーを検出してトリミングする座標を決定する
        aruco_ids: [左上、右上、右下、左下]
        ※各マーカーの内側の角から、さらに内側にシフトした位置をトリミング座標にする
        ※マーカーの周囲に白い枠が必要だが、白い枠は検出対象外＆数字検出時に不都合が生じるので削っている
        """
        id_set = set(aruco_ids)
        params = aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_CONTOUR # 場合によってはこちらのほうがよい&はやい
        aruco_corners, ids, _ = aruco.detectMarkers(img,ARUCO_DICT,parameters=params)
        if set(ids.T[0]) != id_set:
            # 四隅を検出できない場合は、パラメータを調整して再チャレンジ
            params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_APRILTAG # 広角レンズで歪むときは正確（処理はおそい）
            aruco_corners, ids, _ = aruco.detectMarkers(img,ARUCO_DICT,parameters=params)
            if set(ids.T[0]) != id_set:
                return None
        b = [aruco_corners[np.where(ids==aruco_ids[i])[0][0]][0][i] for i in [0,1,2,3]] # 外側の角 ※角Noはidの並びと同じ
        a = [aruco_corners[np.where(ids==aruco_ids[i])[0][0]][0][j] for i,j in enumerate([2,3,0,1])] # 内側の角
        pos = [i+(i-j)/7 for i,j in zip(a,b)] # 内側に向けて白い部分を削るように座標補正
        corners = {}
        for i,k in enumerate(('TL','TR','BR','BL')):
            corners[f'{k}w'] = round(pos[i][0])
            corners[f'{k}h'] = round(pos[i][1])
        return cls(**corners)

    def _position_type(self):
        if all((0<=v<=1 for v in self._asdict().values())):
            return 'ratio'
        else:
            return 'abs'

    def _array(self, fieldname):
        w = getattr(self,f'{fieldname}w')
        h = getattr(self,f'{fieldname}h')
        return np.array((w,h))

    def _get_size(self, fullsizeh=None,fullsizew=None):
        TR = self._array('TR')
        TL = self._array('TL')
        BL = self._array('BL')
        wid = round(np.linalg.norm(TR - TL))
        hei = round(np.linalg.norm(BL - TL))
        return (wid, hei)

    @classmethod
    def _correct_angles(cls,corners, angle=0):
        """平行四辺形補正：左上と右下の座標と傾き角度から右上と左下座標を補正する
        右上と左下が空欄でも入力済みでも無視"""
        c = corners
        if angle == 0:
            return Corners(c.TLw,c.TLh,c.BRw,c.TLh,c.TLw,c.BRh,c.BRw,c.BRh)
        # 傾きがある場合は再計算
        TR = np.array((c.BRw,c.TLh))
        BL = np.array((c.TLw,c.BRh))
        TL = c._array('TL')
        BR = c._array('BR')
        yokoT_vector = (TR - TL) / np.linalg.norm(TR - TL)
        yokoB_vector = (BR - BL) / np.linalg.norm(BR - BL)
        tateL_distance = np.linalg.norm(BL - TL)
        tateR_distance = np.linalg.norm(BR - TR)
        tmp_TR = TR + yokoT_vector * tateR_distance * math.tan(math.radians(angle))
        tmp_BL = BL - yokoB_vector * tateL_distance * math.tan(math.radians(angle))
        # 整数変換
        TRw = round(tmp_TR[0])
        TRh = round(tmp_TR[1])
        BLw = round(tmp_BL[0])
        BLh = round(tmp_BL[1])
        return Corners(c.TLw,c.TLh,TRw,TRh,BLw,BLh,c.BRw,c.BRh)

    def _calc_transform_matrix(self):
        """トリミング用の座標変換行列を作成
        ratio の場合は使用しない"""
        tr = [self._array(x) for x in ('TL','TR','BR','BL')]
        p_original = np.array(tr, dtype=np.float32)
        wid, hei = self._get_size()
        p_trans = np.array([[0,0],[wid,0],[wid,hei],[0,hei]], dtype=np.float32)
        trans_mat = cv2.getPerspectiveTransform(p_original,p_trans)
        trans_size = (wid,hei)
        return trans_mat, trans_size

    def _get_corners(self,img):
        w,h,*other = img.shape
        size = {'w':w, 'h':h}
        c = {f: round(getattr(self,f)*size[f[-1]]) for f in self._fields}
        print(c)
        return c


class Display:
    """4点で囲まれた範囲の切り抜き
    """
    def __init__(self,corners=None,aruco_ids=[],corners_ratio=None):
        self.corners = corners
        self.corners_ratio = corners_ratio
        self.aruco_ids = aruco_ids

    def trim(self, original_image):
        if self.corners_ratio is not None:
            return self.trim_from_ratio(original_image)
        elif len(self.aruco_ids) == 4:
            self.corners = Corners.from_aruco_markers(original_image)
            self.corners._calc_transform_matrix()
            return cv2.warpPerspective(original_image, self.trans_matrix, self.get_image_size(), flags=cv2.INTER_CUBIC)
        elif self.corners is not None:
            return trim_image(original_image, self.corners)
        else:
            raise ValueError

    def trim_from_ratio(self, original_image):
        fullsizeh, fullsizew, *other = original_image.shape # 白黒カラーどちらでも
        corners = self.get_corners_from_ratio(original_image)
        wid, hei = corners._get_size(fullsizeh, fullsizew)
        tr = [self.corners._array(x) for x in ('TL','TR','BR','BL')] # numpy用の順番
        p_original = np.array(tr, dtype=np.float32)
        p_trans = np.array([[0,0],[wid,0],[wid,hei],[0,hei]], dtype=np.float32)
        trans_matrix = cv2.getPerspectiveTransform(p_original,p_trans)
        return cv2.warpPerspective(original_image, trans_matrix, (wid,hei), flags=cv2.INTER_CUBIC)

    def get_corners_from_ratio(self, original_image):
        """ 割合換算された座標と全体画像からふつうの座標を生成
        """
        names = self.corners_ratio._fields
        w,h,*other = original_image.shape
        size = {'w':w, 'h':h}
        c = {f: round(getattr(self.corners_ratio,f)*size[f[-1]]) for f in names}
        return Corners(**c)

    def set_ratio(self, original_image, corners):
        """ ふつうの座標と全体画像から割合換算した座標を生成して保持
        """
        names = corners._fields
        w,h,*other = original_image.shape
        size = {'w':w, 'h':h}
        c = {f: getattr(corners,f)/size[f[-1]] for f in names}
        self.corners_ratio = Corners(**c)

# ======================================================================
# 画像処理汎用
# ======================================================================
def rotate_image(img,angle:int=0):
    """画像の回転 0, 90, 180, 270° のみ（マイナス不可）"""
    if angle == 90:
        rrr = cv2.ROTATE_90_CLOCKWISE
    elif angle == 180:
        rrr = cv2.ROTATE_180
    elif angle == 270:
        rrr = cv2.ROTATE_90_COUNTERCLOCKWISE
    else:
        return img
    rotated_img = cv2.rotate(img,rrr)
    return rotated_img

def testimshow(im):
    f,a = plt.subplots()
    a.imshow(im,cmap='gray')
    plt.show()

def calculate_thresh_auto(img,morpho=True,white=255):
    arr = img
    # 全体の明るさより枠部分が明るいとき白黒反転して文字を白くする
    if (np.average(arr[0]) + np.average(arr[-1]))/2 > np.average(arr):
        arr = cv2.bitwise_not(img)
    # 自動設定しきい値で白黒を強調する
    _, thresh_img = cv2.threshold(arr,0,white,cv2.THRESH_OTSU)
    # ノイズを減らす（良いとは限らない）
    if morpho:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(1,5))
        thresh_img = cv2.morphologyEx(thresh_img, cv2.MORPH_OPEN, kernel)
    return thresh_img

def __nonzerolist(in_list):
    # in_listのゼロでない範囲start,endのリストを作成
    a = []
    start_, end_ = 0, 0
    for i, x in enumerate(in_list):
        if x > 0:
            if i > 0 and in_list[i-1] == 0:
                start_ = i
            elif i == len(in_list)-1:
                end_ = i
                a.append((start_, end_))
        else:
            if i == 0:
                continue
            if in_list[i-1] > 0:
                end_ = i
                a.append((start_, end_))
    return a

def __cut_zeros(x_array):
    # 画像上下のゼロ（黒）部分を削除
    in_list = np.sum(x_array, axis=1)
    start_, end_ = 0, 0
    for i, x in enumerate(in_list):
        if x > 0:
            start_ = i
            break
    for i, x in enumerate(reversed(in_list)):
        if x > 0:
            end_ = len(in_list) - i
            break
    return start_, end_, #x_array[start_:end_]

def __calc_transform_mat(corners):
    """トリミング用の座標変換行列を作成"""
    tr = [corners._array(x) for x in ('TL','TR','BR','BL')]
    p_original = np.array(tr, dtype=np.float32)
    wid, hei = corners._get_size() ############## fullsize
    p_trans = np.array([[0,0],[wid,0],[wid,hei],[0,hei]], dtype=np.float32)
    trans_mat = cv2.getPerspectiveTransform(p_original,p_trans)
    trans_size = (wid,hei)
    return trans_mat, trans_size

def __transform(img, trans_mat,trans_size):
    """指定した変換行列を使ってトリミング"""
    if isinstance(trans_mat, list):
        return img
    else:
        return cv2.warpPerspective(img, trans_mat, trans_size, flags=cv2.INTER_CUBIC)

def trim_aruco_markers(img, aruco_ids):
    """画像のarucoマーカーを使ってトリミング"""
    corners = Corners._from_aruco_markers(img, aruco_ids)
    trans_mat, trans_size = __calc_transform_mat(corners)
    img_trimed = __transform(img,trans_mat, trans_size)
    return img_trimed

def trim_image(img,corners):
    trans_mat, trans_size = __calc_transform_mat(corners)
    img_trimed = __transform(img,trans_mat, trans_size)
    return img_trimed

def search_segments(img):
#    size = img.shape # imgがNoneでないとき
    img_arr = img
    # 数字を切り離してトリミング
    # 縦に区切り--> 上下の空白を削除
    tate_wa = np.sum(img_arr, axis=0)
    segsy = __nonzerolist(tate_wa)
    if len(segsy) == 0:
        return [], []
    segs_tmp = [img_arr[:,x:y] for x,y in segsy]
    segsx = [__cut_zeros(img_arr[:,x[0]:x[1]]) for x in segsy]
    segments = [img_arr[x[0]:x[1],y[0]:y[1]] for x,y in zip(segsx,segsy)]
    coordinates = [(x[0],x[1],y[0],y[1]) for x,y in zip(segsx, segsy)]
    # あまりに小さい領域は削除
    min_size = max([x.shape[1] for x in segments]) / 8
    newseg, newcoo = [], []
    for i,s in enumerate(segments):
        if s.shape[0] > min_size and s.shape[1] > min_size:
            newseg.append(s)
            newcoo.append(coordinates[i])
    return newseg, newcoo

def read_segment(img,max_height):
    # セグメント分割したパーツの数字を読む
    # return: 文字, 参考用のdigit組み合わせ
    Sheight, Swidth = img.shape
    aspect_rate = Sheight / Swidth
    wid = int(Swidth*0.05) if Swidth > 20 else 1
    hei = int(Sheight*0.05) if Sheight > 20 else 1
    mid = (int(Swidth/2)-wid, int(Swidth/2)+wid)
    upp = (int(Sheight*0.25)-hei, int(Sheight*0.25)+hei)
    dwn = (int(Sheight*0.75)-hei, int(Sheight*0.75)+hei)
    if Sheight * 5 < max_height:
        if aspect_rate < 0.4:
            return "-", None # 横長
        else:
            return ".", None
    elif Sheight * 1.8 < max_height:
        if 0.4 < aspect_rate < 3:
            h, w = Sheight/3, Swidth/5
            darks = [
            np.average(img[0:int(h),0:int(w)]),
            np.average(img[0:int(h),int(w*4):Swidth]),
            np.average(img[int(h*2):Sheight,0:int(w)]),
            np.average(img[int(h*2):Sheight,int(w*4):Swidth]),
            ]
            segments = [
            np.average(img[0:int(h),int(w*2):int(w*3)]),
            np.average(img[int(h):int(h*2),0:Swidth]),
            np.average(img[int(h*2):Sheight,int(w*2):int(w*3)]),
            ]
            if all((all((d<s for d in darks)) for s in segments)):
                return "+", None
        else:
            return "", None # +/-も読めるようにしたい
    if aspect_rate >= 4:
        return "1", (0,0,1,0,0,1,0)
    elif 1.1 < aspect_rate < 4:
        # 閾値 または 中心の黒い部分 よりも明るい場合はセグメント検出
        thresh_darkest = 20
        darkest = max(thresh_darkest, (np.average(img[upp[0]:upp[1],mid[0]:mid[1]]) + np.average(img[dwn[0]:dwn[1],mid[0]:mid[1]])) /2)
        segments = [
            np.average(img[0:int(Sheight/3),mid[0]:mid[1]]),
            np.average(img[upp[0]:upp[1],0:int(Swidth/3)]),
            np.average(img[upp[0]:upp[1],int(Swidth*2/3):-1]),
            np.average(img[int(Sheight/3):int(Sheight*2/3),mid[0]:mid[1]]),
            np.average(img[dwn[0]:dwn[1],0:int(Swidth/3)]),
            np.average(img[dwn[0]:dwn[1],int(Swidth*2/3):-1]),
            np.average(img[int(Sheight*2/3):,mid[0]:mid[1]])
            ]
        t = tuple([int(s > darkest) for s in segments])
        if t in DIGITS_LOOKUP:
            return DIGITS_LOOKUP[t], t
        else:
            return "*", t
    else: return "", None

def get_digit(im, corners):
    if im is None:
        return "", []
    trimed_img = trim_image(im,corners)
    th = calculate_thresh_auto(trimed_img)
    segs, coordinates = search_segments(th)
    max_height = max([x[1]-x[0] for x in coordinates])
    result = [read_segment(i,max_height) for i in segs]
    res = "".join([x[0] for x in result])
    segments = [x[1] for x in result]
    return res, segments, coordinates

def get_better_coordinates(good_results_list):
    # (str, segments, [(x,x,y,y),,,]) のリスト 
    print(good_results_list[0])
    max_strlen = max([len(str(x[0])) for x in good_results_list])
    # 数値はたいてい右寄せの数字になっているので、右端から処理する
    for i in range(1,max_strlen+1):
        temp = {".":[],"updown":[],"rightleft":[]}
        for res, segments, coordinates in good_results_list:
            if len(res) < max_strlen: continue
            r = res[-i]
            s = segments[-i]
            if s is None:
                if r == ".":
                    temp["."].append(coordinates[-i])
                else:
                    continue
            else:
                if s[0] and s[6]: # 上下があるセグメント
                    temp["updown"].append(coordinates[-i])
                if (s[2] or s[5]) and (s[1] or s[4]): # 左右があるセグメント
                    temp["rightleft"].append(coordinates[-i])
        # 平均と中央値をとる
        x_medians, y_medians, d_medians = None, None, None
        if len(temp["updown"]) > 0:
            y_medians = [[statistics.median_high(xy[i]) for xy in temp["updown"] if len(xy) == 4] for i in (2,3)]
        if len(temp["rightleft"]) > 0:
            x_medians = [[statistics.median_high(xy[i]) for xy in temp["rightleft"] if len(xy) == 4] for i in (0,1)]
        if len(temp["."]) > 0:
            d_medians = [[statistics.median_high(xy[i]) for xy in temp["."] if len(xy) == 4] for i in ramge(4)]
        print(f"{x_medians = }   {y_medians = }   {d_medians}")


def find_separated_angles(original_img, corners):
    # 文字が縦に揃うとき、縦の和がゼロになる列数が最も多いと思われる
    count, rr = 0,0
    zero_num_list = []
    angle_range = range(-11,21)
    for i,r in enumerate(angle_range):
        dd = Corners._correct_angles(corners,r)
        im_trim = trim_image(original_img, dd)
        th = calculate_thresh_auto(im_trim)
        tate_wa = np.sum(th,axis=0)
        yoko_wa = np.sum(th,axis=1)
        zeros_t = len(tate_wa)-np.count_nonzero(tate_wa)
        zeros_y = len(yoko_wa)-np.count_nonzero(yoko_wa)
        zero_num_list.append(zeros_t)
    zero_angles = [r for r,x in zip(angle_range, zero_num_list) if x == max(zero_num_list)]
    return round(np.average(zero_angles))

def find_lines(original_img, corners):
    # 直線検出
    im = trim_image(original_img, corners)
    im = calculate_thresh_auto(im)
    # 上下の黒い背景を削除
    bg = __cut_zeros(im)
    im = im[bg[0]:bg[1]]
    im = cv2.Canny(im, threshold1=10,threshold2=10,apertureSize=3)
    tatesize = im.shape[0]
    deg = 0
    params = {
        'rho': 1, # default
        'theta': np.pi/360, # default
        'threshold': max((tatesize//50, 2)), # 線として検出する点数
        'maxLineGap': max((tatesize//30, 1)), # 同一の線とみなす点の間隔
        }
    for minlinedev in (4, 6, 8):
        params['minLineLength'] = tatesize//minlinedev # 線として検出する最小長さ
        lines = cv2.HoughLinesP(im,**params)
        if lines is not None and len(lines) > 0:
            angles = [90 - math.atan2((L[0][3]-L[0][1]),(L[0][2]-L[0][0]))*(180/math.pi) for L in lines]
            angles_vertical = [a for a in angles if abs(a) < 15]
            if len(angles_vertical) > 0:
                deg = round(np.average(angles_vertical))
                break
    return deg

def find_good_angle(original_img,corners):
    angle_bg = find_separated_angles(original_img, corners)
    corners_bg = Corners._correct_angles(corners,angle_bg)
    angle_lines = find_lines(original_img, corners_bg)
    corners_both = Corners._correct_angles(corners,angle_bg - angle_lines)
    return corners_both


def testprint(x,y):
    fig,ax = plt.subplots()
    ax.tick_params(top=False,bottom=True,labeltop=False,labelbottom=True)
    ax.set(xlabel='number')
    ax.plot(x,y,marker='.')
    plt.show()
    del fig
    del ax


# ======================================================================
# 動画処理
# ======================================================================
def get_videoimg(videolist, sec):
    # 指定した秒位置の画像を動画から切り出し(複数動画ファイルOK)
    s = sec
    img = None
    for x in videolist:
        fps = x.get(cv2.CAP_PROP_FPS)
        fr = round(fps * s)
        max_frame = int(x.get(cv2.CAP_PROP_FRAME_COUNT))
        if fr < max_frame:
            x.set(cv2.CAP_PROP_POS_FRAMES, fr)
            ret, img = x.read()
            # 特定のフレームが読込みできない場合がある： 1フレームずらす
            # 読めないときは数～数十フレーム続けて読めないことがある
            # ファイル破損することがあるらしい (しかしaviutlでは問題なく開ける  なぜ???)
            # opencv-python のISSUE でも未解決問題らしい
            if not ret:
                x.set(cv2.CAP_PROP_POS_FRAMES, fr+1)
                ret, img = x.read()
            break
        else:
            s -= max_frame / fps
            if s < 0:
                break
    if img is not None:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
#    print(f"video {s=} / {ret=} / {fps=:.2f} / {fr=}")
    return img

def get_videotime(videolist, videofilelist, sec):
    """ ファイル作成日時から逆算して動画の撮影時刻を取得 """
    s = sec
    for x, y in zip(videolist, videofilelist):
        fps = x.get(cv2.CAP_PROP_FPS)
        fr = round(fps * s)
        max_frame = int(x.get(cv2.CAP_PROP_FRAME_COUNT))
        if fr < max_frame:
            # 動画作成日時取得
            ct = y.stat().st_mtime # timestamp
            minussec = (max_frame - fr) / fps
            return dt.fromtimestamp(round(ct - minussec))
        else:
            s -= max_frame / fps
            continue


