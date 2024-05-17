from collections import OrderedDict
import csv
from datetime import datetime as dt
import math
import os
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from idlelib.tooltip import Hovertip

import matplotlib as mpl
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.backend_bases import MouseButton
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import cv2

import readdigits as rd
from readdigits import Corners, Display

APP_TITLE = "画像からデジタル数字を読むプログラム"
APP_VER = rd.version

# ======================================================================
# GUI
# ======================================================================
pads2 = {'padx':2,'pady':2}
pads4 = {'padx':4,'pady':2}
pads8 = {'padx':8,'pady':2}
expandx = {'fill':tk.X}
expandxy = {'fill':tk.BOTH}
framepads = {'padx':4,'pady':4,'anchor':tk.NW,'side':tk.TOP}
iframepads = {'padx':4,'pady':4,'anchor':tk.NW,'side':tk.LEFT}
framepadsw = {'padx':8,'pady':8,'anchor':tk.NW,'side':tk.TOP}
figsize = {'check':(6,3),'trimming':(3,1.5)}

mpl.rcParams['axes.grid'] = True
mpl.rcParams['font.size'] = 10
mpl.rcParams['axes.xmargin'] = .01
mpl.rcParams['axes.ymargin'] = .01
mpl.rcParams['xtick.top'] = True
mpl.rcParams['xtick.bottom'] = False
mpl.rcParams['xtick.labeltop'] = True
mpl.rcParams['xtick.labelbottom'] = False
mpl.rcParams['ytick.right'] = False
mpl.rcParams['figure.constrained_layout.use'] = True

trimming_colors = ('red','cyan','lime','orange')
MAX_TAB_NUM = 3

def modify_dpi():
    import ctypes
    import platform
    if platform.system() == 'Windows' and int(platform.release()) >= 8:
        ctypes.windll.shcore.SetProcessDpiAwareness(True)
modify_dpi()

FRAME_NAMES = Corners._fields
NO_USE = '(使用しない)'

class App(tk.Frame):
    # region Initialize
    def __init__(self, master=None):
        super().__init__(master)
        self.master = master
        self.master.title(f'{APP_TITLE}   ver.{APP_VER}')
        self.fr = {}
        self.val = {}
        self.wid = {}
        self.tid = {}
        for x in ('imgtype','img_dir','video_files','checkimg','video_info',
            'video_spacing_unit','save_dir','save_fname','progress_txt',
            'aruco0_marker'):
            self.val[x] = tk.StringVar(self.master,value='')
        self.val['video_spacing_unit'].set('sec')
        self.val['save_fname'].set('output')
        self.val['aruco0_marker'].set('0-1-2-3')
        
        for x in ('rec_number','rec_filename','rec_created_time','rec_modified_time',
            'rec_timestamp','rec_videotime','rec_videofiletime','rec_value',
            'rotate','video_spacing','checkvideo_sec',
            'progress',
            'aruco0',):
            self.val[x] = tk.IntVar(self.master, value=0)
        self.val['rec_number'].set(1)
        self.val['rec_value'].set(1)
        self.val['rec_videotime'].set(1)
        self.val['rec_videofiletime'].set(1)
        self.val['video_spacing'].set(10)

        self.val['imgtype'].trace_add('write',self.switch_imgtype)
        self.val['video_spacing'].trace_add('write',self.set_video_range)
        self.val['video_spacing_unit'].trace_add('write',self.set_video_range)
#        self.start_trace()

        tkstyle = ttk.Style()
        tkstyle.configure("TButton",width=0)
#        tkstyle.configure("TLabelframe",relief=tk.SUNKEN)
#        tkstyle.configure("TNotebook.Tab",relief='raised')
#        tkstyle.configure("TProgressbar", thickness=10)

        self.notebook = ttk.Notebook(self.master)
        self.tabs = {}
        self.layout_settings()
        self.layout_read()
        self.layout_version()
        self.notebook.pack(**expandxy,**pads2)
        # 値変更時に関数実行したいので、Variable作成時でなくこのタイミングで初期値設定
        self.val['imgtype'].set('image')

    def initialize_allimage(self):
        # 画像関係のウィジェットや変数の初期化
        self.video_captures = []
        self.video_filelist = []
        self.plt_result_x = []
        self.plt_result_y = []
        self.check_image = None
        self.max_videosec = 0
        self.val['img_dir'].set('')
        self.val['checkimg'].set('') # 変数変化に連動して図がリセットされる
        self.val['video_files'].set('')
        self.val['video_info'].set('')
        self.val['checkvideo_sec'].set(0)
        self.val['rotate'].set(0)
        self.val['progress'].set(0)
        self.val['progress_txt'].set('')
        self.wid['checkimg'].config(values=[])
        self.wid['checkvideo_sec'].config(values=[])
        for x in range(MAX_TAB_NUM):
            self.val[f'result{x}'].set('')
            for v in FRAME_NAMES:
                self.val[f'trim{x}_{v}'].set(0)
                self.wid[f'trim{x}_{v}'].config(values=[0,])
        self.clear_graphs()

    # region Layout
    # 見やすくするためレイアウト用のメソッドを分割
    # 別のメソッドから呼び出さない変数はインスタンス変数にせず、数行程度で使い捨てる
    def layout_settings(self):
        tb = "  設定  "
        self.tabs[tb] = ttk.Frame(self.notebook,relief=tk.GROOVE)
#        self.tabs[tb] = ttk.Frame(self.notebook,style="TNotebook.Tab")
        self.notebook.add(self.tabs[tb], text=tb)
        f = ttk.LabelFrame(self.tabs[tb],text='読み取り方式')
        ff = ttk.Frame(f)
        ff.pack(**expandx)
        ttk.Label(f,text='注意： 切り替えると読み込んだ画像をリセットします').pack(**pads2,anchor=tk.NW,side=tk.TOP)
        rad = tk.Radiobutton(ff,text="画像 (.png .jpg)",value='image',variable=self.val['imgtype'])
        rad.pack(**pads2,side=tk.LEFT)
        rad = tk.Radiobutton(ff,text="動画 (.mp4)",value='video',variable=self.val['imgtype'])
        rad.pack(**pads2,side=tk.LEFT)
        f.pack(**framepadsw,**expandx,)

        fr = ttk.LabelFrame(self.tabs[tb],text='読み取りファイル')
        fr.pack(**framepadsw,**expandx)
        Hovertip(fr,'フォルダ名： 日本語OK\nファイル名： ASCII文字のみ可（日本語／全角が入っていると読込みエラー）')
        f = self.fr['img_browse'] = ttk.Frame(fr)
        txt = ttk.Label(f,text="画像フォルダ：")
        txt.pack(**pads4,side=tk.LEFT)
        entryw = ttk.Entry(f,textvariable=self.val['img_dir'])
        entryw.pack(**pads2,**expandx,expand=True,side=tk.LEFT)
        browseButton = ttk.Button(f,text="browse",style="TButton",command=self.browse_img)
        browseButton.pack(**pads2,side=tk.LEFT)
        
        f = self.fr['video_browse'] = ttk.Frame(fr)
        ff = ttk.Frame(f)
        txt = ttk.Label(ff,text="動画ファイル（複数指定可）：")
        txt.pack(**pads4,side=tk.LEFT)
        browseButton = ttk.Button(ff,text="browse",style="TButton",command=self.browse_video)
        browseButton.pack(**pads2,side=tk.LEFT)
        ff.pack(**expandx,anchor=tk.NW)
        Hovertip(ff,'複数指定は動画サイズが大きくなりファイル分割されてしまう場合を想定しています。（Gopro など）\nリストの順番通りに動画を自動的につなげて処理実行します。')
        vlist = tk.Listbox(f,listvariable=self.val['video_files'],height=5)
        vlist.pack(**pads8,**expandx)
        Hovertip(vlist,'動画ファイルのリスト')
        ff = ttk.Frame(f)
        c = ttk.Combobox(ff,width=8,values=['sec','min'],
            textvariable=self.val['video_spacing_unit'],state='readonly')
        c.pack(side=tk.RIGHT,**pads2)
        ttk.Spinbox(ff,width=8,values=[i for i in range(1,101)],
            textvariable=self.val['video_spacing']).pack(side=tk.RIGHT,**pads2)
        ff.pack(**framepads,**expandx)
        
        ttk.Label(ff,text='読み取り間隔：').pack(side=tk.RIGHT,**pads2)
        txt = ttk.Label(ff,textvariable=self.val['video_info'],font=('',12))
        txt.pack(**pads8,**expandx,side=tk.RIGHT)

        f = ttk.LabelFrame(self.tabs[tb],text='保存先')
        ff = ttk.Frame(f)
        ttk.Label(ff,text='フォルダ：').pack(**pads2,side=tk.LEFT)
        ttk.Entry(ff,textvariable=self.val['save_dir']).pack(**pads2,**expandx,expand=True,side=tk.LEFT)
        ttk.Button(ff,text='Browse',style='TButton',command=self.browse_savedir).pack(**pads2,side=tk.LEFT)
        ff.pack(**framepads,**expandx)
        ff = ttk.Frame(f)
        ttk.Label(ff,text='ファイル名：').pack(**pads2,side=tk.LEFT)
        ttk.Entry(ff,textvariable=self.val['save_fname']).pack(**pads2,side=tk.LEFT)
        ttk.Label(ff,text='.csv').pack(**pads2,side=tk.LEFT)
        ff.pack(**framepads,**expandx)
        f.pack(**framepadsw,**expandx)

        f = ttk.LabelFrame(self.tabs[tb],text='csvファイル出力時に書き込む項目')
        tk.Checkbutton(f,text='通し番号',variable=self.val['rec_number']).pack(**pads2,anchor=tk.NW)
        tk.Checkbutton(f,text='読み取った値',state='disabled',variable=self.val['rec_value']).pack(**pads2,anchor=tk.NW)
        ff = self.fr['img_rec'] = ttk.Frame(f)
        tk.Checkbutton(ff,text='画像ファイル名',variable=self.val['rec_filename']).pack(**pads2,anchor=tk.NW)
        tk.Checkbutton(ff,text='画像ファイル作成日時',variable=self.val['rec_created_time']).pack(**pads2,anchor=tk.NW)
        tk.Checkbutton(ff,text='画像ファイル更新日時',variable=self.val['rec_modified_time']).pack(**pads2,anchor=tk.NW)
#        tk.Checkbutton(ff,text='画像のタイムスタンプ',variable=self.val['rec_timestamp']).pack(**pads2,anchor=tk.NW)
#        fff = ttk.Frame(ff)
#        ttk.Label(fff,text='     カメラ機種：').pack(**pads2,anchor=tk.NW,side=tk.LEFT)
#        ttk.Combobox(fff,values=[]).pack(**pads2,anchor=tk.NW,side=tk.LEFT)
#        fff.pack(**pads2,anchor=tk.NW)
        ff = self.fr['video_rec'] = ttk.Frame(f)
        tk.Checkbutton(ff,text='経過再生時間',variable=self.val['rec_videotime']).pack(**pads2,anchor=tk.NW)
#        tk.Checkbutton(ff,text='フレーム数',variable=self.val['rec_videoframe']).pack(**pads2,anchor=tk.NW)
        tk.Checkbutton(ff,text='ファイル保存から逆算した日時',variable=self.val['rec_videofiletime']).pack(**pads2,anchor=tk.NW)
        f.pack(**framepadsw,)

    def layout_read(self):
        tb = "  読み取り範囲指定  "
        self.tabs[tb] = ttk.Frame(self.notebook,relief=tk.GROOVE)
        self.notebook.add(self.tabs[tb], text=tb)
        f = ttk.Frame(self.tabs[tb])
        Hovertip(f,'ここで指定した画像が表示されます。\nまずデジタル数字の範囲（座標）を決めたいので、\n読み取りたい数字の全体が表示されている画像を指定して、\n更新ボタンを押してください。')
        txt = ttk.Label(f,text="チェック用画像：")
        txt.pack(**pads2,side=tk.LEFT)
        ttk.Button(f,text='図の更新',command=self.update_checkimg).pack(**pads8,side=tk.RIGHT)
        self.wid['checkimg'] = ttk.Spinbox(f,values=[''],textvariable=self.val['checkimg'],wrap=True)
        self.wid['checkimg'].pack(**pads2,**expandx)
        ff = self.fr['checkvideo'] = ttk.Frame(f)
        self.wid['checkvideo_sec'] = ttk.Spinbox(ff,values=[0,],textvariable=self.val['checkvideo_sec'],width=10,wrap=True)
        self.wid['checkvideo_sec'].pack(**pads2,side=tk.LEFT)
        ttk.Label(ff,textvariable=self.val['video_spacing_unit']).pack(**pads2,side=tk.LEFT)
        ttk.Label(ff,text=' '*6+'読み取り間隔：').pack(side=tk.LEFT,**pads2)
        ttk.Spinbox(ff,width=8,values=[i for i in range(1,101)],
            textvariable=self.val['video_spacing']).pack(side=tk.LEFT,**pads2)
        c = ttk.Combobox(ff,width=8,values=['sec','min'],
            textvariable=self.val['video_spacing_unit'],state='readonly')
        c.pack(side=tk.LEFT,**pads2)
        f.pack(**framepads,**expandx,)
        f = ttk.Frame(self.tabs[tb])
        ff = tk.Frame(f)
        ttk.Label(ff,text='画像の向き (°)').pack(side=tk.LEFT,**pads2)
        c = ttk.Combobox(ff,values=[0,90,180,270],width=4,textvariable=self.val['rotate'],state='readonly')
        c.pack(side=tk.LEFT,**pads2)
        Hovertip(c,'画像が横向きになっているときは、ここで回転できます。\narucoマーカー使用時は指定不要')
        ff.pack(side=tk.LEFT,padx=12)
        a = ttk.Checkbutton(f,text="arucoマーカー検出 --> IDセット ：",variable=self.val['aruco0'],command=self.update_checkimg)
        a.pack(**pads4,side=tk.LEFT)
        c = ttk.Combobox(f,width=10,values=['0-1-2-3'],textvariable=self.val['aruco0_marker'])
        c.pack(**pads2,side=tk.LEFT)
        Hovertip(c,'左上、右上、右下、左下 に張り付けるマーカーID  それぞれ内側にある角を検出する')
        f.pack()

        f = ttk.Frame(self.tabs[tb])
        self.canvasframe = {}
        self.fig = {}
        self.canvas = {}
        self.ax = {}
        name = 'check'
        self.canvasframe[name] = ttk.Frame(f)
        self.fig[name] = Figure(figsize=figsize[name])
        self.ax[name] = self.fig[name].add_subplot()
        self.canvas[name] = FigureCanvasTkAgg(self.fig[name], self.canvasframe[name])
        self.canvasframe[name].pack()
        self.initialize_graph(name)
        self.canvas[name].mpl_connect('button_press_event', self.get_coordinate_check)
        f.pack(**framepads,**expandx,)
        
        self.notebook_trim = ttk.Notebook(self.tabs[tb])
        self.notebook_trim.pack(**expandxy,**pads2)
        self.tabs_trim = []
        for x in range(MAX_TAB_NUM):
            ft = ttk.Frame(self.notebook_trim,relief=tk.GROOVE)
            #self.tabs_trim.append(ft)
            self.notebook_trim.add(ft,text=f' 数字枠{x+1} ')
            self.val[f'result{x}'] = tk.StringVar(self.master,value='')
            self.val[f'min{x}'] = tk.IntVar(self.master, value=0)
            self.val[f'max{x}'] = tk.IntVar(self.master, value=0)
            self.val[f'check_witheyes{x}'] = tk.IntVar(self.master, value=0)
            self.val[f'min{x}'].trace_add('write',lambda *_,n=x: self.update_minmax(n))
            self.val[f'max{x}'].trace_add('write',lambda *_,n=x: self.update_minmax(n))
            self.val[f'min_num{x}'] = tk.DoubleVar(self.master, value=0)
            self.val[f'max_num{x}'] = tk.DoubleVar(self.master, value=0)
            self.val[f'type{x}'] = tk.StringVar(self.master,value=NO_USE)
            self.val[f'type{x}'].trace_add('write',lambda *_,n=x: self.update_autocorrection(n))

            f = ttk.Frame(ft)
            ff = ttk.Frame(f)
#            fff = tk.Frame(ff,background='red')
            fff = tk.Frame(ff)
            w = ttk.Combobox(fff,width=10,values=[NO_USE,'数値','指数部'],textvariable=self.val[f'type{x}'],state='readonly')
            w.pack(**pads4,side=tk.LEFT)
            fff.pack()
            name = f'trimming{x}'
            figsize[name] = figsize['trimming']
            self.canvasframe[name] = ttk.Frame(ff)
            self.fig[name] = Figure(figsize=figsize[name])
            self.ax[name] = self.fig[name].add_subplot()
            self.canvas[name] = FigureCanvasTkAgg(self.fig[name], self.canvasframe[name])
            self.canvasframe[name].pack(**iframepads)
            self.initialize_graph(name)
            self.canvas[name].mpl_connect('button_press_event', self.get_coordinate_trim)
            ff.pack(**iframepads)
            f.pack(**framepads,**expandx,)
            ff = ttk.LabelFrame(f,text='トリミング範囲')
            fff = ttk.Frame(ff)
            ttk.Label(fff,text="画像を左クリックで左上座標、右クリックで右下座標を取得").pack(**pads2)
            fff.pack(**expandx,)
            fff = ttk.Frame(ff)
            pos = {'左上': ('TL', 0, 0), '右上': ('TR', 0, 3),
                   '左下': ('BL', 1, 0), '右下': ('BR', 1, 3),}
            for k,v in pos.items():
                self.val[f'trim{x}_{v[0]}w'] = tk.IntVar(self.master,value=0)
                self.val[f'trim{x}_{v[0]}h'] = tk.IntVar(self.master,value=0)
                ttk.Label(fff,text=k).grid(row=v[1],column=v[2],**pads2)
                self.wid[f'trim{x}_{v[0]}w'] = ttk.Spinbox(fff,width=6,textvariable=self.val[f'trim{x}_{v[0]}w'])
                self.wid[f'trim{x}_{v[0]}w'].grid(row=v[1],column=v[2]+1,**pads2)
                self.wid[f'trim{x}_{v[0]}h'] = ttk.Spinbox(fff,width=6,textvariable=self.val[f'trim{x}_{v[0]}h'])
                self.wid[f'trim{x}_{v[0]}h'].grid(row=v[1],column=v[2]+2,**pads2)
            fff.pack(**framepads,**expandx,)
            fff = ttk.Frame(ff)
            self.wid[f'btn_autocorrect{x}'] = ttk.Button(fff,text='座標自動補正',style="TButton",
                    state='disabled',command=lambda *_,n=x:self.button_autocorrection(n))
            self.wid[f'btn_autocorrect{x}'].pack(**pads4,side=tk.LEFT)
            txt =  'トリミング用の座標指定： （横、縦）\n\n 左上と右下は必須\n'
            txt += '数字と小数点のラインが重ならず、グリッドに沿うように範囲を調整してください。\n\n'
            txt += '読み取りテスト で小数点分離に失敗する場合は、\n'
            txt += '自動補正のチェックを外し手動で座標を微調整してください。'
            Hovertip(ff,txt)
            t = tk.Label(fff,textvariable=self.val[f'result{x}'],fg="red",font=('',15))
            t.pack(**pads2,side=tk.LEFT)
            fff.pack(**framepads,**expandx,)
            ff.pack(**framepads,**expandx)
            ff = ttk.LabelFrame(f,text='値取得方法')
            fv = ttk.Frame(ff)
            ttk.Checkbutton(fv,text='最小値',variable=self.val[f'min{x}']).pack(**pads2,side=tk.LEFT)
            self.wid[f'min{x}'] = ttk.Entry(fv,textvariable=self.val[f'min_num{x}'],width=5,state='disabled')
            self.wid[f'min{x}'].pack(**pads2,side=tk.LEFT)
            ttk.Label(fv,text='～').pack(**pads2,side=tk.LEFT)
            ttk.Checkbutton(fv,text='最大値',variable=self.val[f'max{x}']).pack(**pads2,side=tk.LEFT)
            self.wid[f'max{x}'] = ttk.Entry(fv,textvariable=self.val[f'max_num{x}'],width=5,state='disabled')
            self.wid[f'max{x}'].pack(**pads2,side=tk.LEFT)
            fv.pack(**expandx)
            Hovertip(fv,'最大・最小値から外れた値をnanにします。')
            ff.pack(**framepads,**expandx,)
            if x == 0:
                self.val[f'type{x}'].set('数値')
        
        w = ttk.Frame(self.tabs[tb])
        f = ttk.Frame(w)
        b = ttk.Button(f,text='読み取り実行',command=self.read_alldata)
        b.pack(**pads4,side=tk.LEFT)
        Hovertip(b,'↑↑↑  上で指定した内容で、画像／動画の全体を読み取り、csv に出力します。')
        ttk.Label(f,text='保存ファイル名：').pack(**pads2,side=tk.LEFT)
        ttk.Entry(f,textvariable=self.val['save_fname']).pack(**pads2,side=tk.LEFT,**expandx)
        ttk.Label(f,text='.csv').pack(**pads2,side=tk.LEFT)
#        tk.Checkbutton(f,text='不明な値は目視確認する[β]',variable=self.val['check_witheyes']).pack(**pads2,side=tk.LEFT)
#        f.pack(**framepads,**expandx)
#        f = ttk.Frame(w)
        ttk.Label(f,textvariable=self.val['progress_txt'],width=10).pack(**pads2,side=tk.RIGHT)
        self.wid['progress'] = ttk.Progressbar(f,variable=self.val['progress'],style='TProgressbar')
        self.wid['progress'].pack(padx=2,**expandx,expand=True,side=tk.LEFT)
        f.pack(**framepads,**expandx)
        b = ttk.Button(w,text='グラフプロット',command=self.plotgraph)
        b.pack(**pads4,anchor=tk.NW)
        Hovertip(b,'読み取り完了後、csv のデータをプロットします。')
        w.pack(**framepads,**expandx)

    def layout_version(self):
        tb = "バージョン"

    # region GUI Functions
    def switch_imgtype(self,*args):
        self.initialize_allimage()
        if self.val['imgtype'].get() == 'video':
            self.fr['img_browse'].pack_forget()
            self.fr['img_rec'].pack_forget()
            self.wid['checkimg'].pack_forget()
            self.fr['video_browse'].pack(**framepads,**expandx)
            self.fr['video_rec'].pack(side=tk.TOP,anchor=tk.N+tk.W)
            self.fr['checkvideo'].pack(**pads2,side=tk.TOP,anchor=tk.N+tk.W,**expandx)
        else:
            self.fr['video_browse'].pack_forget()
            self.fr['video_rec'].pack_forget()
            self.fr['checkvideo'].pack_forget()
            self.fr['img_browse'].pack(**framepads,**expandx)
            self.fr['img_rec'].pack(side=tk.TOP,anchor=tk.N+tk.W)
            self.wid['checkimg'].pack(**pads2,**expandx)

    def browse_img(self):
        s = filedialog.askdirectory()
        if s == '': return
        p = Path(s)
        # cv2 はパスに日本語があると読まないので該当フォルダに移動
        # ファイル名はASCIIのみにする必要あり
        if p.exists():
            os.chdir(str(p.resolve()))
            imglist = [t.name for t in p.glob('*.jpg')] + [t.name for t in p.glob('*.png')]
            self.val['img_dir'].set(str(p.resolve()))
            self.val['save_dir'].set(str(p.resolve()))
            self.wid['checkimg'].config(values=imglist)
            if len(imglist) > 0:
                self.val['checkimg'].set(imglist[0])
            else:
                self.val['checkimg'].set('')

    def browse_video(self):
        s = filedialog.askopenfilenames(filetypes=[("video file",".mp4")])
        ### type(s) = tuple
        if len(s) == 0: return
        self.video_filelist = [Path(x) for x in s]
        self.val['video_files'].set(s)

        # cv2 はパスに日本語があると読まないので該当フォルダに移動
        # ファイル名はASCIIのみにする必要あり
        p = str(self.video_filelist[0].parent.resolve())
        os.chdir(p)
        self.val['save_dir'].set(p)
        vl = [Path(x).name for x in s]
        if len(self.video_captures) > 0:
            for x in self.video_captures:
                x.release()
        try:
            temp = [cv2.VideoCapture(x) for x in vl]
            self.video_captures = [x for x in temp if x.isOpened()]
            self.max_videosec = sum([cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS) for cap in self.video_captures])
        except:
            self.video_captures = []
        if len(self.video_captures) == 0:
            print('動画ファイル読込みに失敗しました')
            self.max_videosec = 0
        self.set_video_range(None)
        
        self.val['video_info'].set(f'video total: {self.max_videosec/60:.1f} min')
        self.set_video_range()

    def browse_savedir(self):
        s = filedialog.askdirectory(initialdir=self.val['save_dir'].get())
        if s == '': return
        p = Path(s)
        if p.exists():
            self.val['save_dir'].set(str(p.resolve()))

    def update_checkimg(self,*args):
        # args: variablename, ??, mode
        self.load_check_img()
        self.show_check_img()

    def update_minmax(self,n):
        state = 'normal' if self.val[f'min{n}'].get() else 'disabled'
        self.wid[f'min{n}'].config(state=state)
        state = 'normal' if self.val[f'max{n}'].get() else 'disabled'
        self.wid[f'max{n}'].config(state=state)

    def clear_graph(self,name):
        self.ax[name].cla()
        self.canvas[name].draw()

    def clear_graphs(self):
        for name in figsize.keys():
            if name == 'trimming':
                continue
            self.clear_graph(name)

    def initialize_graphs(self):
        for name in figsize.keys():
            self.fig[name].clf()
            self.ax[name].cla()
            self.canvas[name].get_tk_widget().destroy()
            fig = Figure(figsize=figsize[name])
            canvas = FigureCanvasTkAgg(fig,self.canvasframe[name])
            canvas.get_tk_widget().pack()
            self.canvas[name], self.fig[name] = canvas, fig
            self.ax[name] = self.fig[name].add_subplot()
            self.canvas[name].draw()

    def set_video_range(self,*args):
        if self.val['video_spacing_unit'].get() == 'min':
            mm = math.ceil(self.max_videosec/60)
        else:
            mm = math.ceil(self.max_videosec)
        try:
            inc = round(self.val['video_spacing'].get())
        except:
            return
        if inc < 1: inc = 1
        self.wid['checkvideo_sec'].config(from_=0,to=mm,increment=inc)
        self.val['checkvideo_sec'].set(0)

    def initialize_graph(self,name):
        fig = Figure(figsize=figsize[name])#, layout='tight')
        canvas = FigureCanvasTkAgg(fig,self.canvasframe[name])
        canvas.get_tk_widget().pack()
        self.canvas[name], self.fig[name] = canvas, fig
        self.ax[name] = self.fig[name].add_subplot()
        self.canvas[name].draw()
        self.trim_mod_x, self.trim_mod_y = 0, 0

    def get_check_img(self):
        check_image = None
        if self.val['imgtype'].get() == 'video':
            if self.val['video_spacing_unit'].get() == 'sec':
                sec = self.val['checkvideo_sec'].get()
            else:
                sec = self.val['checkvideo_sec'].get() * 60
            check_image = rd.get_videoimg(self.video_captures,sec)
        else:
            fn = self.val['checkimg'].get()
            f = Path(fn)
            if f.exists() and f.is_file():
                check_image = cv2.imread(fn,cv2.IMREAD_GRAYSCALE)
            else:
                print('check_image not loaded.')
        if check_image is None:
            return
        angle = self.val['rotate'].get()
        check_image = rd.rotate_image(check_image,angle)
        if self.val['aruco0'].get():
            ids = [int(x) for x in self.val['aruco0_marker'].get().split('-')]
            if len(set(ids)) == 4:
                check_image = rd.trim_aruco_markers(check_image, ids)
        return check_image

    def load_check_img(self):
        self.check_image = self.get_check_img()
        if self.check_image is None:
            return
        # 座標範囲指定
        h,w = self.check_image.shape
        for k in {'TL','BR','BL','TR'}:
            for x in range(MAX_TAB_NUM):
                self.wid[f'trim{x}_{k}w'].config(values=[i for i in range(0,w)])
                self.wid[f'trim{x}_{k}h'].config(values=[i for i in range(0,h)])

    def show_check_img(self):
        # チェック用の全体図を表示  データがなければ図をリセットする
        name = 'check'
        if self.check_image is None:
            self.clear_graphs()
        else:
            self.ax[name].imshow(self.check_image,cmap='gray')
            self.canvas[name].draw()

    def update_autocorrection(self,n):
        if self.val[f'type{n}'].get() == NO_USE:
            self.wid[f'btn_autocorrect{n}'].config(state='disabled')
        else:
            self.wid[f'btn_autocorrect{n}'].config(state='normal')

    def button_autocorrection(self,n):
        # 座標指定したトリミング範囲の図と枠線を表示
        if self.check_image is None:
            self.clear_graphs()
            return
        angle = self.val['rotate'].get()
        d = rd.find_good_angle(self.check_image, Corners(**self.get_trimarea(n)))
        # 対角の座標を自動入力
        for k in ('TRw','BLw','TRh','BLh'):
            self.val[f'trim{n}_{k}'].set(getattr(d,k))

        trimed_image = rd.calculate_thresh_auto(d.trim_image(self.check_image))
        # テスト
        chars, coordinates = rd.get_digit(self.check_image,d)
        txt = "".join(chars)
        wid, hei = d.TLw, d.TLh
        self.trim_mod_x, self.trim_mod_y = wid, hei
        name = f'trimming{n}'
        self.clear_graph(name)
        self.ax[name].grid(False)
        self.ax[name].imshow(trimed_image,cmap='gray')
        self.ax[name].xaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda x, pos: int(x+wid)))
        self.ax[name].yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda x, pos: int(x+hei)))
        ## show lines
        if coordinates is not None:
            for sxy in coordinates: # (x,x,y,y)
                y = [sxy[0],sxy[0],sxy[1],sxy[1],sxy[0]]
                x = [sxy[2],sxy[3],sxy[3],sxy[2],sxy[2]]
                self.ax[name].plot(x,y,color='orange',lw=max(min(trimed_image.shape)//100, 1))
        self.canvas[name].draw()
        ### テキスト更新
        self.val[f'result{n}'].set(txt)
        self.update_check_img()
    
    def update_check_img(self):
        name = 'check'
        self.clear_graph(name)
        self.show_check_img()
        for n in range(MAX_TAB_NUM):
            # 使用しないなら表示しない
            if self.val[f'type{n}'].get() == NO_USE:
                continue
            d = self.get_trimarea(n)
            x = [d['TLw'],d['TRw'],d['BRw'],d['BLw'],d['TLw']]
            y = [d['TLh'],d['TRh'],d['BRh'],d['BLh'],d['TLh']]
            self.ax[name].plot(x,y,color=trimming_colors[n],marker='.',)
        self.canvas[name].draw()

    def read_alldata(self):
        savepath = Path(self.val['save_dir'].get()) / Path(self.val['save_fname'].get()+'.csv')
        angle = self.val['rotate'].get()
        results = []
        displays_lookup = [n for n in range(MAX_TAB_NUM) if self.val[f'type{n}'].get() != NO_USE]
        corners = {tabnum: Corners(**self.get_trimarea(tabnum)) for tabnum in displays_lookup}
        displays = {tabnum: Display() for tabnum in displays_lookup}
        for tabnum, d in displays.items():
            d.set_ratio(self.check_image, corners[tabnum])

        mode = self.val['imgtype'].get()
        preprocess_aruco = self.val['aruco0'].get()
        st = dt.now()
        markers = [int(x) for x in self.val['aruco0_marker'].get().split('-')]
        if mode == 'image':
            records = OrderedDict([(x, self.val[f'rec_{x}'].get()) 
                for x in ['number','created_time','modified_time','filename']])
            for n in displays_lookup:
                records[f'value{n}'] = True
            p = Path(self.val['img_dir'].get())
            os.chdir(str(p.resolve()))
            image_filelist = [t for t in p.glob('*.jpg')] + [t for t in p.glob('*.png')]
            max_num = len(image_filelist)
            if max_num == 0:
                print(f'no image file exists in {p.resolve()}')
                return
            self.wid['progress'].config(maximum=max_num-1)
            self.val['progress'].set(0)
            for i, file in enumerate(image_filelist):
                self.val['progress'].set(i)
                self.val['progress_txt'].set(f'{i}/{max_num}')
                self.wid['progress'].update()
                im = cv2.imread(file.name,cv2.IMREAD_GRAYSCALE)
                temp = {
                    'number':i,
                    'created_time':str(dt.fromtimestamp(file.stat().st_ctime)), # unix timestamp --> datetime
                    'modified_time':str(dt.fromtimestamp(file.stat().st_mtime)),
                    'filename':file.name,
                    }
                if preprocess_aruco:
                    im = rd.trim_aruco_markers(im, markers)
                for tabnum in displays_lookup:
                    c = displays[tabnum].get_corners_from_ratio(im)
                    valueread, _ = rd.get_digit(im,c)
                    temp[f'txt{tabnum}'] = ''.join(valueread)
                results.append(temp)
        else:
            records = OrderedDict([(x, self.val[f'rec_{x}'].get()) 
                for x in ['number','videotime','videofiletime',]])
            for n in displays_lookup:
                records[f'value{n}'] = True
            if len(self.video_captures) == 0:
                print('no video files loaded.')
                return
            time_spacing = self.val['video_spacing'].get()
            if self.val['video_spacing_unit'].get() == 'min':
                tp = 60
            else:
                tp = 1
            time_spacing *= tp
            max_sec = math.ceil(self.max_videosec)
            max_num = max_sec // time_spacing
            self.wid['progress'].config(maximum=max_num)
            self.val['progress'].set(0)
            for i, t in enumerate(range(0,max_sec, time_spacing)):
                self.val['progress'].set(i)
                self.val['progress_txt'].set(f'{i}/{max_num}')
                self.wid['progress'].update()
                im = rd.get_videoimg(self.video_captures, t)
                if preprocess_aruco:
                    im = rd.trim_aruco_markers(im, markers)
                vt = round(t/tp) if tp == 60 else t
                vt_filetime = rd.get_videotime(self.video_captures, self.video_filelist, t)
                temp = {
                    'number':i,
                    'videotime':vt,
                    'videofiletime': vt_filetime,
                    }
                for tabnum in displays_lookup:
                    c = displays[tabnum].get_corners_from_ratio(im)
                    valueread, _ = rd.get_digit(im,c)
                    temp[f'txt{tabnum}'] = ''.join(valueread)
                results.append(temp)
        for num in displays_lookup:
            valuetype = self.val[f'type{num}'].get()
            # max & min の参照
            check_min = self.val[f'min{num}'].get()
            check_max = self.val[f'max{num}'].get()
            min_num = self.val[f'min_num{num}'].get()
            max_num = self.val[f'max_num{num}'].get()
            for x in results:
                if valuetype == '文字列':
                    x[f'value{num}'] = x[f'txt{num}']
                    continue
                try:
                    x[f'value{num}'] = float(x[f'txt{num}'])
                except:
                    x[f'value{num}'] = math.nan
                if check_min and x[f'value{num}'] < min_num: # nan と数値の比較は必ず False になる
                    x[f'value{num}'] = math.nan
                if check_max and x[f'value{num}'] > max_num:
                    x[f'value{num}'] = math.nan
        # csv 書き込み
        header = [x for x,use in records.items() if use]
        results_use = [{k:v for k,v in res.items() if k in header} for res in results]
        with open(savepath,'w',newline='') as f:
            writer = csv.DictWriter(f, header)
            writer.writeheader()
            writer.writerows(results_use)
        self.plt_result_x = [x['number'] for x in results]
        self.plt_result_y = [x[f'value{0}'] for x in results]# for n in displays_lookup]

        self.val['progress_txt'].set('complete.')
        en = dt.now()
        print((en.timestamp()-st.timestamp()))

    def plotgraph(self):
        if len(self.plt_result_x) == len(self.plt_result_y) > 0:
            testprint(self.plt_result_x,self.plt_result_y)

    def get_trimarea(self, n):
        # 座標取得
        return {f'{k}':self.val[f'trim{n}_{k}'].get() for k in FRAME_NAMES}

    def get_coordinate_check(self, event):
        if event.xdata is None: return
        x = int(event.xdata)
        y = int(event.ydata)
        self.__set_coordinate(event.button, x, y)

    def get_coordinate_trim(self, event):
        if event.xdata is None: return
        x = int(event.xdata) + self.trim_mod_x
        y = int(event.ydata) + self.trim_mod_y
        self.__set_coordinate(event.button, x, y)

    def __set_coordinate(self, btn, x, y):
        n = self.get_current_trimtab()
        if btn == MouseButton.LEFT:
            self.val[f'trim{n}_TLw'].set(x)
            self.val[f'trim{n}_TLh'].set(y)
        elif btn == MouseButton.RIGHT:
            self.val[f'trim{n}_BRw'].set(x)
            self.val[f'trim{n}_BRh'].set(y)

    def get_current_trimtab(self):
        tab_id = self.notebook_trim.select()
        tab_txt = self.notebook_trim.tab(tab_id,'text')
        num = int(tab_txt.strip()[-1]) -1
        return num

def testprint(x,y):
    fig,ax = plt.subplots()
    ax.tick_params(top=False,bottom=True,labeltop=False,labelbottom=True)
    ax.set(xlabel='number')
    ax.plot(x,y,marker='.')
    plt.show()
    del fig
    del ax

# region Main
# ======================================================================
# Main
# ======================================================================
def app_main():
    root = tk.Tk()
    root.resizable(1,1)
    app = App(master=root)
    app.mainloop()

app_main()


