"""器件表 —— 全项目**唯一**的元件定义处。

原来 PREFIX / UNIT / PINS / SUPPORTED / 符号 / 引脚 分散在 7 个文件里各写一遍，
加一个电容要改 7 处。现在集中到这里：加新元件 = 加一条记录。

每个器件声明：类型、中文名、位号前缀、单位、引脚、所属域、参数、网表模板、分组。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# 域
DC = "dc"        # 直流稳态
AC = "ac"        # 正弦稳态（相量）
TRAN = "tran"    # 暂态 / 时域


@dataclass(frozen=True)
class Device:
    type: str
    cn: str                                  # 中文名
    prefix: str                              # 位号前缀 R/C/L/V/I/...
    unit: str
    pins: Tuple[Tuple[str, float, float], ...] = (("p0", 0.0, -30.0), ("p1", 0.0, 30.0))
    domains: Tuple[str, ...] = (DC, AC, TRAN)
    params: Tuple[str, ...] = ("value",)     # 需要用户填的参数
    group: str = "dc"                        # 元件库分组
    linear: bool = True                      # 非线性器件要迭代
    probes: Tuple[str, ...] = ()             # 可探测的支路量（v/i/p）
    note: str = ""
    extra: Dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 引脚约定（与前端画布一致）：
#   纵向元件（电阻/电容/电感/多数源）：p0 在上(-30)、p1 在下(+30)，随 rotation 旋转
#   横向元件（受控源的控制端另加 c0/c1）
# ---------------------------------------------------------------------------
V = (("p0", 0.0, -30.0), ("p1", 0.0, 30.0))
H = (("p0", -30.0, 0.0), ("p1", 30.0, 0.0))

DEVICES: Dict[str, Device] = {}


def _reg(d: Device) -> Device:
    DEVICES[d.type] = d
    return d


# ---------------- 无源 ----------------
_reg(Device("resistor", "电阻", "R", "Ω", H, params=("value",), probes=("v", "i", "p"),
            note="u=Ri，串联相加、并联倒数相加"))
_reg(Device("capacitor", "电容", "C", "F", H, domains=(AC, TRAN), params=("value",),
            probes=("v", "i", "q", "w"), note="i=C·du/dt；相量 Z=1/(jωC)"))
_reg(Device("inductor", "电感", "L", "H", H, domains=(AC, TRAN), params=("value",),
            probes=("v", "i", "w"), note="u=L·di/dt；相量 Z=jωL"))

# ---------------- 独立源 ----------------
# params 里多一个 kind：dc / ac / step / sin  → 决定网表写法
_reg(Device("vsource", "电压源", "V", "V", V, params=("value", "kind", "freq", "phase"),
            group="dc", probes=("v", "i", "p"), note="理想电压源；kind=ac 时为正弦相量源"))
_reg(Device("isource", "电流源", "I", "A", V, params=("value", "kind", "freq", "phase"),
            group="dc", probes=("v", "i", "p"), note="理想电流源；方向：从 p1 穿过源、注入 p0"))

# ---------------- 三相 ----------------
_reg(Device("vsource3", "三相电源", "U", "V", (("p0", 0.0, -60.0), ("p1", 0.0, -20.0),
                                                ("p2", 0.0, 20.0), ("p3", 0.0, 60.0)),
            domains=(AC,), params=("value", "freq", "phase"), group="ac",
            probes=("v", "i"), note="三相对称电源：U 相 0°、V 相 −120°、W 相 +120°"))

# ---------------- 受控源 ----------------
_reg(Device("vcvs", "压控电压源", "E", "×", (("p0", 0.0, -30.0), ("p1", 0.0, 30.0),
                                             ("c0", -30.0, 0.0), ("c1", 30.0, 0.0)),
            params=("gain",), group="ac", probes=("v", "i"), note="u2 = μ·u1"))
_reg(Device("vccs", "压控电流源", "G", "S", (("p0", 0.0, -30.0), ("p1", 0.0, 30.0),
                                             ("c0", -30.0, 0.0), ("c1", 30.0, 0.0)),
            params=("gain",), group="ac", probes=("v", "i"), note="i2 = gm·u1"))
_reg(Device("ccvs", "流控电压源", "H", "Ω", (("p0", 0.0, -30.0), ("p1", 0.0, 30.0)),
            params=("gain", "control"), group="ac", probes=("v", "i"), note="u2 = r·i1"))
_reg(Device("cccs", "流控电流源", "F", "×", (("p0", 0.0, -30.0), ("p1", 0.0, 30.0)),
            params=("gain", "control"), group="ac", probes=("v", "i"), note="i2 = β·i1"))

# ---------------- 磁路 ----------------
_reg(Device("transformer", "理想变压器", "T", "×", (("p0", -30.0, -30.0), ("p1", -30.0, 30.0),
                                                    ("p2", 30.0, -30.0), ("p3", 30.0, 30.0)),
            params=("ratio",), group="ac", probes=("v", "i"),
            note="u1/u2 = n，i1/i2 = −1/n；阻抗折合 = n²·ZL"))

# ---------------- 半导体 ----------------
_reg(Device("diode", "二极管", "D", "V", H, params=("vth", "rd"), group="semi",
            linear=False, probes=("v", "i"), note="分段线性：导通 0.7V + rd，截止开路"))
_reg(Device("zener", "稳压管", "DZ", "V", H, params=("vz", "rd"), group="semi",
            linear=False, probes=("v", "i"), note="分段线性：正向 0.7V，反向击穿 Vz"))
_reg(Device("bjt", "三极管", "Q", "×", (("b", -20.0, 0.0), ("c", 20.0, -30.0), ("e", 20.0, 30.0)),
            params=("beta", "vbe", "type"), group="semi", linear=False,
            note="直流：Vbe≈0.7V、Ic=βIb；交流：微变等效 rbe=rbb'+β·26mV/Ic"))
_reg(Device("opamp", "集成运放", "A", "×", (("inp", -30.0, 10.0), ("inn", -30.0, -10.0),
                                            ("out", 30.0, 0.0)),
            params=("model",), group="opamp", linear=False,
            note="理想：虚短虚断；A→∞，输出电流由外电路决定"))
_reg(Device("switch", "开关", "S", "-", H, params=("closed",), group="tran",
            linear=False, probes=("v", "i"), note="闭合=短路，断开=开路"))
_reg(Device("ground", "接地", "GND", "V", (("p0", 0.0, 0.0),), domains=(DC, AC, TRAN),
            params=(), group="dc", probes=(), note="参考点 0V"))

# ---------------- 查询接口 ----------------
def get(type_: str) -> Device:
    d = DEVICES.get(type_)
    return d if d else DEVICES["resistor"]


def unit_of(type_: str) -> str:
    return get(type_).unit


def prefix_of(type_: str) -> str:
    return get(type_).prefix


def pins_of(type_: str) -> List[Tuple[str, float, float]]:
    return list(get(type_).pins)


def groups() -> Dict[str, List[Device]]:
    out: Dict[str, List[Device]] = {}
    for d in DEVICES.values():
        if d.type == "ground":
            continue
        out.setdefault(d.group, []).append(d)
    return out


def takes_value(type_: str) -> bool:
    """这个器件的「值」是不是用户填的数值（value）？
    二极管用 vth/rd、三极管用 beta/vbe、运放无参、开关用 closed —— 这些**没有 value**，
    绝不能因为 value 为空就被当成「未知量」去反解。
    """
    if type_ == "ground":
        return False
    return "value" in get(type_).params


GROUP_CN = {"dc": "直流", "ac": "交流/受控源", "tran": "动态/开关",
            "semi": "半导体", "opamp": "运算放大器", "digital": "数字"}
