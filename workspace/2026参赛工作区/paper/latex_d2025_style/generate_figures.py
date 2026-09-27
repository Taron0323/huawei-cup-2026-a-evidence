"""Generate editable illustrative placeholders, never empirical contest results."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, fontManager

ROOT = Path(__file__).resolve().parent
FONT = Path("/Applications/Microsoft Word.app/Contents/Resources/DFonts/Simsun.ttc")
if FONT.exists():
    fontManager.addfont(str(FONT))
    family = FontProperties(fname=str(FONT)).get_name()
else:
    family = "FandolSong"
plt.rcParams.update({"font.family": family, "font.size": 11, "axes.unicode_minus": False,
                     "pdf.fonttype": 42, "savefig.bbox": "tight", "axes.spines.top": False,
                     "axes.spines.right": False})
OUT = ROOT / "figures"
OUT.mkdir(exist_ok=True)
rng = np.random.default_rng(2025)


def save(fig, name):
    fig.text(.5, .005, "示意数据 / 排版占位，不表示赛题计算结果", ha="center", fontsize=9, color="#555555")
    fig.savefig(OUT / f"{name}.pdf", pad_inches=.12)
    fig.savefig(OUT / f"{name}.png", dpi=130, pad_inches=.12)
    plt.close(fig)


def flow(name, rows):
    fig, ax = plt.subplots(figsize=(9, max(3.0, len(rows) * 1.0)))
    ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis("off")
    ys = np.linspace(.88, .13, len(rows))
    for i, (y, row) in enumerate(zip(ys, rows)):
        xs = np.linspace(.19, .81, len(row)) if len(row) > 1 else [.5]
        for x, label in zip(xs, row):
            ax.text(x, y, label, ha="center", va="center", fontsize=12,
                    bbox={"boxstyle": "square,pad=0.65", "fc": "#f1f6fa" if i % 2 == 0 else "#f6f1e9", "ec": "#536b79", "lw": .9})
            if i < len(rows) - 1:
                next_xs = np.linspace(.19, .81, len(rows[i+1])) if len(rows[i+1]) > 1 else [.5]
                targets = next_xs if len(row) == 1 else [min(next_xs, key=lambda value: abs(value-x))]
                for next_x in targets:
                    ax.annotate("", xy=(next_x, ys[i+1]+.055), xytext=(x,y-.055),
                                arrowprops={"arrowstyle":"->", "color":"#56636c", "lw":1})
    save(fig, name)


flows = {
"background": [["地面自动站", "风廓线与辐射计", "天气雷达"], ["多源观测与质量控制"], ["低空风险场", "给定空域航路"]],
"roadmap": [["观测数据", "地理信息", "数值天气预报"], ["问题一：模型 a 与模型 b"], ["问题二：三维重构模型 c"], ["模型 d：NWP 标定", "模型 e：观测外推"], ["风险代价、路径搜索与验证"]],
"symbols": [["T、p、u、v、w、SW"], ["位温 θ", "稳定度 Ri", "切变 S"], ["无量纲风险指标 I"], ["路径 π 与累计风险 C"]],
"analysis": [["信息缺失", "尺度不同", "未来变化"], ["双模型标定", "观测算子融合", "滚动回报"], ["逐点误差、场误差与路径验证"]],
"assumptions": [["配对与观测假设", "空间与动态假设"], ["参数扰动", "分组留出"], ["误差变化、适用范围与方案选择"]],
"q1flow": [["雷达资料", "辐射计资料"], ["对齐、质量控制与参数计算"], ["模型 a：热力与动力", "模型 b：雷达特征"], ["约束回归", "随机森林"], ["时间块检验与垂直廓线输出"]],
"learning": [["训练时间块", "验证时间块", "测试时间块"], ["训练期归一化与模型拟合"], ["固定参数后的预测"], ["整体指标", "分高度指标", "残差分析"]],
"q2flow": [["地面站", "廓线雷达", "S / X 波段雷达"], ["时间基准、空间坐标和共同指标"], ["各向异性 IDW 基线"], ["观测项", "背景项", "平滑项"], ["变分融合、误差场与地图输出"]],
"support": [["原始输入与说明"], ["配置", "程序", "环境"], ["逐点结果", "验证指标", "路径序列"], ["图、表、公式参数与正文结论"]],
"ai": [["实际采用的 AI 输出"], ["工具四字段", "采用位置", "输入记录"], ["队伍理解、复算与修订"], ["结果旁标注", "代码前标注", "汇总记录"]],
"modelselection": [["回归标定", "空间重构", "时间预测"], ["岭回归基线", "IDW 基线", "持续性基线"], ["非线性 / 变分 / 动态候选"], ["相同输入、相同划分、相同指标"]],
}
for name, rows in flows.items():
    flow(name, rows)

t = np.linspace(0, 180, 31)
z = np.linspace(25, 1975, 40)
tt, zz = np.meshgrid(t, z)
field = np.clip(.28 + .19*np.sin(tt/38)*np.exp(-zz/2200) + .16*np.cos(zz/360), 0, 1)


def heatmaps(name, labels):
    fig, axs = plt.subplots(1,len(labels),figsize=(10,3.4),squeeze=False)
    for j, (ax,label) in enumerate(zip(axs[0],labels)):
        data = np.clip(field+.035*j*np.sin(tt/25+zz/190),0,1)
        im=ax.pcolormesh(t,z,data,cmap="viridis",vmin=0,vmax=1,shading="auto")
        ax.set(title=label,xlabel="相对时间 / min",ylabel="高度 / m")
        fig.colorbar(im,ax=ax,shrink=.8,label="归一化示意值")
    fig.tight_layout(rect=(0,.05,1,1));save(fig,name)


heatmaps("parameters2d",["风速特征", "谱宽特征", "热力特征"])
heatmaps("fielda",["模型 a 的时间-高度分布"])
heatmaps("fieldb",["模型 b 的时间-高度分布"])
heatmaps("weather",["温度特征", "风速特征", "变化特征"])
heatmaps("weathercombined",["地面约束", "雷达约束", "融合输入"])

for name in ["parameters3d","field3d","fusion3d"]:
    fig=plt.figure(figsize=(8,4.6));ax=fig.add_subplot(projection="3d")
    xx,yy=np.meshgrid(np.linspace(0,5,30),np.linspace(0,5,30))
    vv=.3+.3*np.exp(-((xx-2.5)**2+(yy-2.3)**2))
    for h in [250,750,1250,1750]:
        ax.scatter(xx.ravel(),yy.ravel(),np.full(xx.size,h),c=(vv*np.exp(-h/4000)).ravel(),cmap="viridis",vmin=0,vmax=1,s=4,alpha=.6)
    ax.set(xlabel="局部 X / km",ylabel="局部 Y / km",zlabel="高度 / m")
    ax.view_init(elev=23,azim=-58);save(fig,name)

fig,axs=plt.subplots(2,3,figsize=(10,5))
for ax,label,color in zip(axs.flat,["水平风速","垂直速度","谱宽","温度","信噪比","切变"],["#85c1dc","#96cf9a","#ba9cc9","#e6bb73","#73bdb3","#7e9dbf"]):
    ax.hist(rng.normal(size=300),bins=18,color=color,edgecolor="black",linewidth=.3)
    ax.set(title=label,xlabel="标准化示意值",ylabel="样本数")
fig.tight_layout(rect=(0,.06,1,1));save(fig,"distribution")

fig,axs=plt.subplots(1,3,figsize=(10,4.1))
for j,ax in enumerate(axs):
    ax.plot(3+j+np.sin(z/230+j),z,color=["#2487b1","#b87842","#5b9c75"][j])
    ax.set(xlabel=["U 示意值","V 示意值","W 示意值"][j],ylabel="高度 / m");ax.grid(alpha=.2)
fig.tight_layout(rect=(0,.05,1,1));save(fig,"wind")

fig,ax=plt.subplots(figsize=(6,4.5))
for j,(label,color,ls) in enumerate([( "模型 a","#222222","-"),("原始模型 b","#cb784c","--"),("优化模型 b","#3187b1","-.")]):
    ax.plot(.45+.15*np.sin(z/320)+j*.045*np.cos(z/200),z,label=label,color=color,ls=ls)
ax.set(xlabel="无量纲风险示意值",ylabel="高度 / m");ax.legend();ax.grid(alpha=.2);save(fig,"profiles")

fig,axs=plt.subplots(1,2,figsize=(9,3.3))
axs[0].bar(["稳定度","谱宽","切变"],[.35,.4,.25],color=["#b589ae","#76abca","#96b493"])
axs[0].set(ylabel="示意权重")
for j in range(3):axs[1].plot(np.linspace(0,1,30),np.linspace(0,1,30)**(j+1),label=f"参数组 {j+1}")
axs[1].set(xlabel="参数取值",ylabel="响应示意值");axs[1].legend();fig.tight_layout(rect=(0,.06,1,1));save(fig,"coefficients")

fig,axs=plt.subplots(1,2,figsize=(9,3.4));x=np.linspace(.05,.95,80);e=rng.normal(0,.04,len(x))
axs[0].scatter(x,x+e,s=13,color="#347fa3");axs[0].plot([0,1],[0,1],color="black",ls="--")
axs[0].set(xlabel="参照示意值",ylabel="预测示意值");axs[1].scatter(x,e,s=13,color="#ad8250")
axs[1].axhline(0,color="black",ls="--");axs[1].set(xlabel="预测示意值",ylabel="残差示意值")
fig.tight_layout(rect=(0,.06,1,1));save(fig,"residuals")

for name in ["stationqc","stations"]:
    fig,axs=plt.subplots(1,2,figsize=(9,3.5))
    for j,ax in enumerate(axs):
        xs=rng.uniform(0,5,35);ys=rng.uniform(0,5,35)
        ax.scatter(xs,ys,c=xs+ys,cmap="viridis",s=25)
        ax.scatter([1,4],[3,1],marker="^",s=110,c="#bf654a",label="雷达示意站")
        ax.set(xlabel="局部 X / km",ylabel="局部 Y / km",title=["观测空间位置","覆盖与质量示意"][j]);ax.legend(fontsize=9)
    fig.tight_layout(rect=(0,.06,1,1));save(fig,name)

for name in ["nwp","forecast","departure"]:
    fig,axs=plt.subplots(1,2,figsize=(9,3.4));ts=np.arange(20);base=.5+.13*np.sin(ts/3)
    axs[0].plot(ts,base,color="#2c7c9c",label="中心预测示意")
    axs[0].fill_between(ts,base-.05-.003*ts,base+.05+.003*ts,color="#91bdd0",alpha=.5,label="区间示意")
    axs[0].set(xlabel="时效或窗口索引",ylabel="风险示意值");axs[0].legend(fontsize=9)
    axs[1].bar(["持续性","线性","非线性","集成"],[.22,.19,.17,.16],color=["#aab1b5","#b99878","#77a4b8","#88b395"])
    axs[1].set(ylabel="误差或代价示意值");fig.tight_layout(rect=(0,.06,1,1));save(fig,name)

fig,axs=plt.subplots(1,2,figsize=(9,4));x=np.linspace(0,5,80);xx,yy=np.meshgrid(x,x)
f=.15+.65*np.exp(-((xx-2.6)**2+(yy-2.4)**2)/.75)
for ax in axs:
    ax.pcolormesh(x,x,f,cmap="YlOrRd",vmin=0,vmax=1,shading="auto")
    ax.plot([.4,4.6],[.4,4.6],"--",c="#333333",label="基准示意路径")
    ax.plot([.4,.8,1.3,3.6,4.6],[.4,2.4,4.2,4.5,4.6],c="#177ea2",lw=2,label="优化示意路径")
    ax.set(xlabel="局部 X / km",ylabel="局部 Y / km");ax.legend(fontsize=8)
fig.tight_layout(rect=(0,.04,1,1));save(fig,"routes")

fig,axs=plt.subplots(2,2,figsize=(9,5.8))
axs[0,0].pcolormesh(t,z,field,cmap="viridis",shading="auto");axs[0,0].set(title="历史重构",xlabel="时间 / min",ylabel="高度 / m")
axs[0,1].plot(t,field.mean(axis=0),color="#347d9c");axs[0,1].set(title="风险变化",xlabel="时间 / min",ylabel="风险示意值")
axs[1,0].pcolormesh(x,x,f,cmap="YlOrRd",shading="auto");axs[1,0].plot([.4,.8,1.3,3.6,4.6],[.4,2.4,4.2,4.5,4.6],c="#177ea2");axs[1,0].set(title="路径示意",xlabel="X / km",ylabel="Y / km")
axs[1,1].bar(["基线","模型 d","模型 e"],[.24,.18,.20],color=["#acb0b2","#5b99b5","#a7b886"]);axs[1,1].set(title="指标对照",ylabel="示意误差")
fig.tight_layout(rect=(0,.05,1,1));save(fig,"finalresults")

fig,axs=plt.subplots(1,2,figsize=(9,3.4))
xs=np.linspace(.5,1.5,9)
for j in range(3):axs[0].plot(xs,.15+.05*j+.12*(xs-1)**2,marker="o",label=f"参数 {j+1}")
axs[0].legend();axs[0].set(xlabel="相对参数值",ylabel="误差示意值")
axs[1].bar(["完整","去设备 A","去设备 B","去时间项"],[.16,.23,.20,.19],color="#79a5ba")
axs[1].set(ylabel="误差示意值");fig.tight_layout(rect=(0,.06,1,1));save(fig,"sensitivity")
print(f"Generated {len(list(OUT.glob('*.pdf')))} illustrative vector figures")
