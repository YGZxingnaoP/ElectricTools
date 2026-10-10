"""拓扑推导：几何原理图 → 电气节点（DSU）+ 稳定 NodeID。

拓扑规则：
- 端子/导线端点共点必连；
- 导线端落在另一导线中部（T 接）自动连；
- 十字交叉默认不连；junction 显式强制连；
- 接地并入节点 0；
- NodeID 采用「历史复用」保证编辑过程稳定。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from .models import Component, Diagnostic, Schematic

COORD_Q = 1000.0        # 坐标量化精度（1/1000）
ON_WIRE_TOL = 2.0       # 点落在导线上的容差（几何单位）
GND_KEY = "__GND__"


def _q(v: float) -> int:
    return int(round(v * COORD_Q))


def _point_on_segment(pt, a, b, tol: float = ON_WIRE_TOL) -> bool:
    px, py = pt
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0.0:
        return (px - ax) ** 2 + (py - ay) ** 2 <= tol * tol
    t = ((px - ax) * dx + (py - ay) * dy) / l2
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return (px - cx) ** 2 + (py - cy) ** 2 <= tol * tol


def _point_on_polyline(pt, verts) -> bool:
    for i in range(len(verts) - 1):
        if _point_on_segment(pt, verts[i], verts[i + 1]):
            return True
    return False


class _DSU:
    def __init__(self) -> None:
        self._p: Dict[str, str] = {}

    def add(self, k: str) -> None:
        self._p.setdefault(k, k)

    def find(self, k: str) -> str:
        self.add(k)
        root = k
        while self._p[root] != root:
            root = self._p[root]
        while self._p[k] != root:
            self._p[k], k = root, self._p[k]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._p[rb] = ra


class NodeRegistry:
    """跨多次求解维持 NodeID 稳定（见 drawing-model §4.2）。"""

    def __init__(self) -> None:
        self._prev: Dict[str, Set[str]] = {}
        self._counter = 0

    def assign(self, groups: List[Tuple[Set[str], bool]]) -> Dict[frozenset, str]:
        """groups: [(members, is_ground)] → {members_frozenset: nodeId}"""
        result: Dict[frozenset, str] = {}
        used_prev: Set[str] = set()
        new_groups: List[Set[str]] = []

        for members, is_ground in groups:
            key = frozenset(members)
            if is_ground:
                result[key] = "0"
                continue
            best, best_score = None, 0
            for pid, pmembers in self._prev.items():
                if pid == "0" or pid in used_prev:
                    continue
                score = len(pmembers & members)
                if score > best_score:
                    best, best_score = pid, score
            if best is not None:
                used_prev.add(best)
                result[key] = best
            else:
                new_groups.append(members)

        # 新节点按「锚点」确定性编号（锚 = 成员键的最小值），保证首次求解编号可预期
        for members in sorted(new_groups, key=lambda s: min(s) if s else ""):
            self._counter += 1
            result[frozenset(members)] = f"n{self._counter}"

        self._prev = {nid: set(key) for key, nid in result.items()}
        return result


@dataclass
class TopologyResult:
    node_of_member: Dict[str, str] = field(default_factory=dict)
    nodes: Dict[str, Dict] = field(default_factory=dict)
    branches: List[Dict] = field(default_factory=list)
    diagnostics: List[Diagnostic] = field(default_factory=list)


def derive_topology(sch: Schematic, registry: NodeRegistry) -> TopologyResult:
    res = TopologyResult()
    dsu = _DSU()

    conn: List[Tuple[float, float, str]] = []  # (x, y, member_key)
    all_keys: List[str] = []

    # 导线
    for w in sch.wires:
        if len(w.vertices) < 2:
            continue
        wkey = f"w:{w.id}"
        dsu.add(wkey)
        all_keys.append(wkey)
        v0, vN = w.vertices[0], w.vertices[-1]
        conn.append((v0.x, v0.y, wkey))
        conn.append((vN.x, vN.y, wkey))

    # 元件端子
    for c in sch.components:
        if not c.pins:
            continue
        if c.type == "ground":
            dsu.add(GND_KEY)
            for p in c.pins:
                k = f"u:{c.id}/{p.name}"
                dsu.add(k)
                all_keys.append(k)
                dsu.union(k, GND_KEY)
                # 接地引脚同样参与「共点合并」，才能与同坐标的导线/端子并成节点 0
                conn.append((p.x, p.y, k))
        else:
            for p in c.pins:
                k = f"u:{c.id}/{p.name}"
                dsu.add(k)
                all_keys.append(k)
                conn.append((p.x, p.y, k))

    # junction
    for j in sch.junctions:
        k = f"j:{j.id}"
        dsu.add(k)
        all_keys.append(k)
        conn.append((j.x, j.y, k))

    # ① 共点合并
    groups: Dict[Tuple[int, int], List[str]] = {}
    for x, y, key in conn:
        groups.setdefault((_q(x), _q(y)), []).append(key)
    for g in groups.values():
        for k in g[1:]:
            dsu.union(g[0], k)

    # ② T 接：连接点落在导线内部
    for w in sch.wires:
        if len(w.vertices) < 2:
            continue
        verts = [(v.x, v.y) for v in w.vertices]
        wkey = f"w:{w.id}"
        for x, y, key in conn:
            if key == wkey:
                continue
            if _point_on_polyline((x, y), verts):
                dsu.union(wkey, key)

    # ③ 汇总
    roots: Dict[str, Set[str]] = {}
    # 只有真的存在接地元件时，才引入 __GND__ 组；否则会凭空造出一个空的「节点 0」，
    # 让「是否有地」的判断恒为真、并把数值解引到无意义的基准上。
    keys = set(all_keys)
    if any(c.type == "ground" for c in sch.components):
        keys.add(GND_KEY)
    for k in keys:
        roots.setdefault(dsu.find(k), set()).add(k)

    groups_list: List[Tuple[Set[str], bool]] = []
    for members in roots.values():
        is_ground = GND_KEY in members
        groups_list.append((members, is_ground))

    id_by_members = registry.assign(groups_list)

    for members, is_ground in groups_list:
        nid = id_by_members[frozenset(members)]
        for m in members:
            if m == GND_KEY:
                continue
            res.node_of_member[m] = nid
        res.nodes[nid] = {
            "id": nid,
            "is_ground": is_ground,
            "members": sorted(m for m in members if m != GND_KEY),
        }

    # ④ 支路
    for c in sch.components:
        if c.type == "ground":
            continue
        pin_keys = [f"u:{c.id}/{p.name}" for p in c.pins]
        if len(pin_keys) < 2:
            res.diagnostics.append(
                Diagnostic(level="warn", code="DANGLING", message=f"元件 {c.id} 端子不足，已跳过。")
            )
            continue
        np_ = res.node_of_member.get(pin_keys[0])
        nn_ = res.node_of_member.get(pin_keys[1])
        # 多端子器件（受控源控制端、变压器副边、运放、三极管）也把全部端子的节点带上，
        # 并且把元件参数（kind/freq/phase/gain/ratio/control/closed…）一并带出，
        # 这样符号通道和数值引擎都能直接拿到。
        nodes = {}
        for pin in c.pins:
            nid = res.node_of_member.get(f"u:{c.id}/{pin.name}")
            if nid is not None:
                nodes[pin.name] = nid
        params = dict(getattr(c, "params", None) or {})
        if c.value is not None:
            params.setdefault("value", c.value)
        if c.symbol:
            params.setdefault("symbol", c.symbol)
        res.branches.append(
            {
                "component": c.id,
                "type": c.type,
                "node_p": np_,
                "node_n": nn_,
                "value": c.value,
                "symbol": c.symbol,
                "unit": c.unit,
                "nodes": nodes,
                "params": params,
            }
        )

    return res
