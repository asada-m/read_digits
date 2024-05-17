# region Define
from pathlib import Path
import math
from datetime import datetime as dt
from typing import NamedTuple
import numpy as np
import cv2
from cv2 import aruco

version = __version__ = "0.63"

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
# region Class Corners
class Corners(NamedTuple):
    """切り抜き用の座標
    np.array 形式を呼び出すときは インスタンス._array(角の名前/whなし)
    """
    TLw: float  # Top-Left width
    TLh: float  # Top-Left height
    TRw: float  # Top-Right width
    TRh: float  # Top-Right height
    BLw: float  # Bottom-Left width
    BLh: float  # Bottom-Left height
    BRw: float  # Bottom-Right width
    BRh: float  # Bottom-Right height

    @classmethod
    def _from_2corners(cls, TLw, TLh, BRw, BRh):
        """左上・右下の座標のみ指定して四隅座標を取得
        """
        return cls(TLw,TLh,BRw,TLh,TLw,BRh,BRw,BRh)

    @classmethod
    def _from_aruco_markers(cls, img:np.array, aruco_ids:list):
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

    def _array(self, fieldname:str):
        w = getattr(self,f'{fieldname}w')
        h = getattr(self,f'{fieldname}h')
        return np.array((w,h))

    def _get_size(self):
        TR = self._array('TR')
        TL = self._array('TL')
        BL = self._array('BL')
        wid = round(np.linalg.norm(TR - TL))
        hei = round(np.linalg.norm(BL - TL))
        return (wid, hei)

    @classmethod
    def _correct_angles(cls,corners, angle:int=0):
        """平行四辺形補正：左上と右下の座標と傾き角度から右上と左下座標を補正する
        右上と左下が空欄でも入力済みでも無視
        
        一度 Corners を作成してから補正して再作成する
        """
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

    def trim_image(self, img):
        trans_mat, trans_size = self._calc_transform_matrix()
        img_trimed = transform(img,trans_mat, trans_size)
        return img_trimed

    @classmethod
    def _mod(cls,corners,key,mod):
        w, h = corners._get_size()
        modw = round(mod/100*w)
        d = corners._asdict()
        d[key] += modw
        return cls(**d)


# region Class Display
class Display:
    """4点で囲まれた範囲の切り抜き
    """
    def __init__(self,corners:Corners=None,aruco_ids=[],corners_ratio=None):
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
            return self.corners.trim_image(original_image)
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

# region Utils for Images
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

def calculate_thresh_auto(img,morpho=True,white=255):
    """グレースケール画像を白黒に変換"""
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
    """in_listのゼロでない範囲start,endのリストを作成"""
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

def __cut_zeros(x_array, dim=2):
    """画像上下のゼロ（黒）部分を削除"""
    if dim == 2:
        in_list = np.sum(x_array, axis=1)
    elif dim == 1:
        in_list = x_array
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

def transform(img, trans_mat,trans_size):
    """指定した変換行列を使ってトリミング"""
    if isinstance(trans_mat, list):
        return img
    else:
        return cv2.warpPerspective(img, trans_mat, trans_size, flags=cv2.INTER_CUBIC)

def trim_aruco_markers(img, aruco_ids):
    """画像のarucoマーカーを使ってトリミング"""
    corners = Corners._from_aruco_markers(img, aruco_ids)
    trans_mat, trans_size = corners._calc_transform_matrix()
    img_trimed = transform(img,trans_mat, trans_size)
    return img_trimed

def __search_char(img):
    """白黒画像から文字領域を切り出し"""
    img_arr = img
    # 数字を切り離してトリミング
    # 縦に区切り--> 上下の空白を削除
    tate_wa = np.sum(img_arr, axis=0)
    segsy = __nonzerolist(tate_wa)
    if len(segsy) == 0:
        return [], []
    #segs_tmp = [img_arr[:,x:y] for x,y in segsy]
    segsx = [__cut_zeros(img_arr[:,x[0]:x[1]]) for x in segsy]
    segs_temp = [img_arr[x[0]:x[1],y[0]:y[1]] for x,y in zip(segsx,segsy)]
    coor_temp = [(x[0],x[1],y[0],y[1]) for x,y in zip(segsx, segsy)]
    # あまりに小さい領域は削除
    min_size = max([min(x.shape) for x in segs_temp]) / 10
    char_imgs = [s for s in segs_temp if s.shape[0] > min_size and s.shape[1] > min_size]
    coordinates = [c for s,c in zip(segs_temp,coor_temp) if s.shape[0] > min_size and s.shape[1] > min_size]
    return char_imgs, coordinates

def read_char(char_img,max_height):
    # セグメント分割したパーツの数字を読む
    # return: 文字, 参考用のdigit組み合わせ
    img = char_img
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

def get_digit(im, corners:Corners):
    if im is None:
        return "", []
    trimed_img = corners.trim_image(im)
    th = calculate_thresh_auto(trimed_img)
    segs, coordinates = __search_char(th)
    max_height = max([x[1]-x[0] for x in coordinates])
    result = [read_char(i,max_height)[0] for i in segs]
    print(result)
    return result, coordinates

"""def __test_():
    segs, coordinates = separate_dots(trimed_img)
    max_height = max([x[1]-x[0] for x in coordinates])
    result = [read_char(i,max_height) for i in segs]
    segments = [x[1] for x in result]
    # test
    coordinates = assemble_bars(result, segments, coordinates)
    print(coordinates)
    imgs = [trimed_img[c[0]:c[1],c[2]:c[3]] for c in coordinates]
    result = [read_char(i,max_height) for i in imgs]
    #segments = [x[1] for x in result]
    res = "".join([x[0] for x in result])
    return res, coordinates"""

# region Fine-tuning
def find_good_angle(original_img,corners,type='number'):
    #デジタル数字の傾きがまっすぐになるように座標補正する
    #文字が縦に揃うとき、縦の和がゼロになる列数が最も多いと思われる
    zero_num_list = []
    angle_range = range(-11,21)
    for r in angle_range:
        dd = Corners._correct_angles(corners,r)
        im_trim = dd.trim_image(original_img)
        th = calculate_thresh_auto(im_trim)
        tate_wa = np.sum(th,axis=0)
        #yoko_wa = np.sum(th,axis=1)
        zeros_t = len(tate_wa)-np.count_nonzero(tate_wa)
        #zeros_y = len(yoko_wa)-np.count_nonzero(yoko_wa)
        zero_num_list.append(zeros_t)
    zero_angles = [r for r,x in zip(angle_range, zero_num_list) if x == max(zero_num_list)]
    angle_bg = round(np.average(zero_angles))
    corners_bg = Corners._correct_angles(corners,angle_bg)
    # 直線検出して傾き補正
    im = calculate_thresh_auto(corners_bg.trim_image(original_img))
    bg = __cut_zeros(im)
    im = cv2.Canny(im[bg[0]:bg[1]], threshold1=10,threshold2=10,apertureSize=3)
    tatesize = im.shape[0]
    angle_lines = 0
    HoughLine_params = {
        'rho': 1, # default
        'theta': np.pi/360, # default
        'threshold': max((tatesize//50, 2)), # 線として検出する点数
        'maxLineGap': max((tatesize//30, 1)), # 同一の線とみなす点の間隔
        }
    for minlinedev in (4, 6, 8):
        HoughLine_params['minLineLength'] = tatesize//minlinedev # 線として検出する最小長さ
        lines = cv2.HoughLinesP(im,**HoughLine_params)
        if lines is not None and len(lines) > 0:
            angles = [90 - math.atan2((L[0][3]-L[0][1]),(L[0][2]-L[0][0]))*(180/math.pi) for L in lines]
            angles_vertical = [a for a in angles if abs(a) < 15]
            if len(angles_vertical) > 0:
                angle_lines = round(np.average(angles_vertical))
                break
    corners_res = Corners._correct_angles(corners,angle_bg - angle_lines)
    if type == 'number':
        # 小数点を含む場合はさらに補正
        chars, _ = get_digit(original_img, corners_res)
        try:
            _ = float(''.join(chars))
            # 数値判定できて小数点が存在する場合は調整なし
            if '.' in chars:
                return corners_res
        except:
            pass
        check = [i for i in range(3,9,3)] + [i for i in range(-3,-9,-3)]
        res_dot = None
        # 小数点を検出できるように四隅右上の座標を微調整する
        for i in check:
            for key in ('TRw',): # 'BLw'):
                c2 = Corners._mod(corners_res,key,i)
                chars, _ = get_digit(original_img, c2)
                try:
                    _ = float(''.join(chars))
                except:
                    continue
                if '.' in chars:
                    res_dot = c2
        if res_dot is not None:
            corners_res = res_dot
    return corners_res

def separate_dots(trimed_img):
    """数字にくっついている小数点を分割する"""
    th = calculate_thresh_auto(trimed_img)
    char_imgs, coordinates = __search_char(th)
    max_height = max([x[1]-x[0] for x in coordinates])
    char_imgs_, coordinates_ = [], []
    for char_img, coordinate in zip(char_imgs,coordinates):
        ch, switch = read_char(char_img, max_height)
        if ch.isdigit(): # 右側のセグメントがONのとき(数字は全部そう)
            not_dots = [(len(img)-__cut_zeros(img,dim=1)[0]) > len(img)/5 for img in char_img.T]
            if all(not_dots): # not all の書き方がわからなかった
                char_imgs_.append(char_img)
                coordinates_.append(coordinate)
                continue
            # 後ろ側からdotぽい(False)が続くとき
            # 下から少し浮いた小数点の場合もある
            dotlen = 0
            for i,p in enumerate(reversed(not_dots)):
                if p is True:
                    dotlen = i
                    break
            if len(char_img[0])/10 < dotlen < len(char_img[0])/3: # 横の長さに対して一定割合のとき
                # 分割
                c = coordinate
                cnum = (c[0],c[1],c[2],c[3]-dotlen)
                char_imgs_.append(th[cnum[0]:cnum[1],cnum[2]:cnum[3]])
                coordinates_.append(cnum)
                temp = th[:,c[3]-dotlen:c[3]]
                st,en = __cut_zeros(temp)
                cdot = (st,en,c[3]-dotlen,c[3])
                char_imgs_.append(th[cdot[0]:cdot[1],cdot[2]:cdot[3]])
                coordinates_.append(cdot)
                continue
        char_imgs_.append(char_img)
        coordinates_.append(coordinate)
    return char_imgs_, coordinates_

def __compare_segment(tuplea,tupleb):
    """数字判定されたAの各セグメントがBと一致するかどうか"""
    if not isinstance(tuplea,tuple):
        return False
    c = [a==b if b in (1,0) else True for a, b in zip(tuplea,tupleb)]
    return all(c)

def assemble_bars(res, segments, coordinates):
    """数字の縦棒の間隔が広く、傾き補正時に別々の領域に分離してしまう場合、本体の横棒とくっつける
    分離した棒は'' または 1 になっているはず
    """
    if not any([r in res for r in ('','1')]):
        # 読み取れない文字や1が含まれない場合は処理しない
        return coordinates
    pops = []
    for i, r in enumerate(res):
        if __compare_segment(segments[i],(None,0,None,None,0,None,None,)):
            # 左の棒がないとき
            if i > 0 and res[i-1] in ('', '1'):
                wid_self = coordinates[i][1]-coordinates[i][0]
                wid_bar = coordinates[i-1][1]-coordinates[i-1][0]
                gap = coordinates[i][0]-coordinates[i-1][1]
                if gap < wid_bar and wid_bar *2 < wid_self:
                    # barが十分細くて隙間が狭いときくっつける
                    pops.append((i,-1))
            # 右の棒がないとき
            if i < len(res)-1 and res[i+1] in ('', '1'):
                wid_self = coordinates[i][1]-coordinates[i][0]
                wid_bar = coordinates[i+1][1]-coordinates[i+1][0]
                gap = coordinates[i+1][0]-coordinates[i][1]
                if gap < wid_bar and wid_bar *2 < wid_self:
                    # barが十分細くて隙間が狭いときくっつける
                    pops.append((i,0))
    while(len(pops) > 0):
        p = pops.pop(0)
        main = coordinates.pop(p[0])
        con = coordinates.pop(p[0]+p[1])
        if p[1] == -1:
            # 左と結合
            res = (con[0],main[1],min((con[2],main[2])),max((con[3],main[3])))
        else:
            # 右と結合
            res = (main[0],con[1],min((con[2],main[2])),max((con[3],main[3])))
        coordinates.insert(p[0]+p[1],res)
        for pp in pops:
            if pp[0] > p[0]:
                pp[0] -= 1
    return coordinates

# region Utils for Movies
# ======================================================================
# 動画処理
# ======================================================================
def get_videoimg(videolist, sec):
    """ 指定した秒位置の画像を動画から切り出し(複数動画ファイルOK)"""
    s = sec
    img = None
    ct = 0
    for x in videolist:
        fps = x.get(cv2.CAP_PROP_FPS)
        fr = round(fps * s)
        max_frame = int(x.get(cv2.CAP_PROP_FRAME_COUNT))
        ms = round(s*1000)
        if fr < max_frame:
            x.set(cv2.CAP_PROP_POS_FRAMES, fr)
            # x.set(cv2.CAP_PROP_POS_MSEC, ms)
            ret, img = x.read()
            # 特定のフレームが読込みできない場合がある： 1フレームずらす
            # 読めないときは数～数十フレーム続けて読めないことがある
            # ファイル破損することがあるらしい (しかしaviutlでは問題なく開ける  なぜ???)
            # opencv-python のISSUE でも未解決問題らしい(?)
            # コーデックの問題でmp4でない場合もある(?)
            if not ret:
                ct +=1
                x.set(cv2.CAP_PROP_POS_FRAMES, fr-1)
            # x.set(cv2.CAP_PROP_POS_MSEC, ms+1)
                ret, img = x.read()
            break
        else:
            s -= max_frame / fps
            if s < 0:
                break
    if img is not None:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
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

# region Others

def print_aruco_markers(savedir,markerIDs:list=[0,1,2,3],base=20):
    """装置ディスプレイに貼り付け用のarucoマーカー画像を作成してsavedirに4種類出力する
    markerID[左上,右上,右下,左下]を指定可
    テプラ等で印刷したあと、黒枠の外側に白い部分が残らないようにハサミで切り抜いてから、装置に貼ってください。
    savedir: 保存先フォルダ
    markerIDs: IDセット
    base: 画像パーツのサイズ（テプラ印刷なら20くらいでOK）
    """
    marker_names = [("Top","Left"),("Top","Right"),("Bottom","Right"),("Bottom","Left")]
    mgn = base//2
    size_mark = 6*base # 生成するマーカーのサイズ
    fillL = base*6
    fillS = mgn
    max_wid = fillL+fillS+size_mark+mgn*2
    fface = cv2.FONT_HERSHEY_DUPLEX
    fscale = base/20
    ft = round(base/15) if base/20 > 1.4 else 1
    for m,id in zip(marker_names,markerIDs):
        img_mark = ARUCO_DICT.generateImageMarker(id, size_mark)
        txtmgn = base//3 if "Bottom" in m else base//2
        if "Left" in m:
            img_ = np.concatenate([np.full((size_mark,fillL+mgn),255),img_mark,np.full((size_mark,fillS+mgn),255)],1)
            cv2.putText(img_,m[0],(mgn+txtmgn,round(base*1.5)),fface,fscale,0,ft)
            cv2.putText(img_,m[1],(mgn+txtmgn,round(base*3.5)),fface,fscale,0,ft)
            cv2.putText(img_,f'ID:{id}',(mgn+txtmgn,round(base*5.5)),fface,fscale,0,ft)
        else:
            img_ = np.concatenate([np.full((size_mark,fillS+mgn),255),img_mark,np.full((size_mark,fillL+mgn),255)],1)
            cv2.putText(img_,m[0],(fillS+mgn+size_mark+txtmgn,round(base*1.5)),fface,fscale,0,ft)
            cv2.putText(img_,m[1],(fillS+mgn+size_mark+txtmgn,round(base*3.5)),fface,fscale,0,ft)
            cv2.putText(img_,f'ID:{id}',(fillS+mgn+size_mark+txtmgn,round(base*5.5)),fface,fscale,0,ft)
        img_ = np.concatenate([np.full((fillS+mgn,max_wid),255),img_,np.full((fillS+mgn,max_wid),255)],0)
        for n in range(mgn):
            # 縁は黒で塗りつぶし
            cv2.rectangle(img_,(n,n),(max_wid-n,size_mark+fillS*2+mgn*2-n),0,thickness=1)
        fn = (Path(savedir)/Path(f"marker_{m[0]}{m[1]}.jpg")).resolve().as_posix()
        cv2.imwrite(fn,img_)

