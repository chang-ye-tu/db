"""B+ tree：每個節點是一頁（slotted page），槽依鍵排序。

第 7 章的定義 7.1.4（B+ tree）、演算法 7.1.8（找葉，find_leaf）與 7.1.10（範圍查詢，range），
以及命題 7.1.12（樹高的界限）；葉容量 L、分支上限 F 在這裡以 bytes 計（項目等長時就是個數）。

  * 葉（LEAF）：每個槽是一個項目 (鍵, RID)，依 (鍵, RID) 排序；標頭的 next 指向右邊的葉。
    鍵可以重複：同一個鍵的不同 RID 是不同的項目，所以項目兩兩不同。
  * 內部節點（INNER）：標頭的 next 是最左邊的子節點 c0；第 i 個槽是 (分隔項目 s_i, 子節點 c_i)。
    c0 放小於 s_1 的項目，c_i 放大於或等於 s_i、小於 s_{i+1} 的項目。

搜尋從根往下，每一層讀一頁（visits 計算讀了幾個節點）；範圍查詢到了葉之後沿著葉鏈往右走。
插入時葉放不下就分裂，分隔項目「複製」到上一層；內部節點放不下也分裂，中間的分隔項目「搬」到上一層。
刪除只從葉移除項目，不合併節點。

分隔項目只在需要時帶 RID：左右兩邊的鍵不同時，分隔項目是 (鍵, LOW_RID)（PostgreSQL 稱為 suffix truncation）。
根的頁號建立後就不變（catalog 只記一次）：根分裂時，把根的內容搬到新的一頁，根改寫成新的內部節點。
鍵裡有 NULL 的列不放進索引（PostgreSQL 會放，見第 7.7 節）。
"""

import struct
from bisect import bisect_left, bisect_right

from .buffer import BufferPool
from .page import HEADER, INNER, LEAF, NONE, SLOT, SlottedPage
from .record import Schema

_RID = struct.Struct(">IH")       # (頁號, 槽號)
_CHILD = struct.Struct(">I")
LOW_RID = (-1, -1)                # 比任何 RID 都小：(鍵, LOW_RID) 排在這個鍵所有的項目之前
_LOW_RID_CODE = (NONE, 0xFFFF)    # LOW_RID 在頁裡的寫法（真的 RID 不會用到頁號 NONE）


class _Sorted:
    """把一個節點看成排好序的序列：bisect 做二分搜尋時，只解碼比較到的那幾個槽（P2 的 bisect）。"""

    def __init__(self, node: SlottedPage, decode):
        self.node, self.decode = node, decode

    def __len__(self) -> int:
        return self.node.n_slots

    def __getitem__(self, i: int):
        return self.decode(self.node.get(i))


def _used(page: SlottedPage) -> int:
    return len(page.data) - page.free_space()


def _split_point(recs: list[bytes], lo: int, hi: int) -> int:
    """分裂點 m：前 m 筆的 bytes 剛好達到全部的一半。鍵的長度不固定，所以按 bytes 分，不按個數分。"""
    total, acc = sum(len(r) + SLOT for r in recs), 0
    for m, r in enumerate(recs, start=1):
        acc += len(r) + SLOT
        if 2 * acc >= total:
            return min(max(m, lo), hi)
    return hi


def _before_lo(key: tuple, lo, inclusive: bool) -> bool:
    """key 在下界之前？lo 是鍵的前綴，只比較 key 的前 len(lo) 欄。"""
    if lo is None:
        return False
    head = key[:len(lo)]
    return head < lo or (head == lo and not inclusive)


def _after_hi(key: tuple, hi, inclusive: bool) -> bool:
    """key 在上界之後？hi 是鍵的前綴。"""
    if hi is None:
        return False
    head = key[:len(hi)]
    return head > hi or (head == hi and not inclusive)


class BPlusTree:
    """B+ tree（定義 7.1.4）：一個節點一頁；葉放 (鍵, RID)，內部節點放分隔項目與子節點，葉串成葉鏈。"""

    def __init__(self, pool: BufferPool, root: int, key_schema: Schema):
        self.pool, self.root, self.key = pool, root, key_schema
        self.visits = 0                              # 讀了幾個節點（= 幾頁）
        self._last_visit = None
        # 一個項目最多佔可用空間的 1/4：分裂後的兩半一定放得下（習題 7.2.2）
        self.max_entry = (pool.pager.page_size - HEADER) // 4

    @staticmethod
    def create(pool: BufferPool) -> int:
        """配置一棵空樹（一片空的葉當根），傳回根的頁號。"""
        f = pool.new_page(LEAF)
        pool.unpin(f.page_no)
        return f.page_no

    # ------------------------------------------------------------- 編碼
    def _leaf_rec(self, key: tuple, rid) -> bytes:
        """(鍵, RID) → 葉的一個槽：RID 6 bytes，接著鍵的記錄。"""
        return _RID.pack(*rid) + self.key.encode(key)

    def _leaf_entry(self, rec: bytes) -> tuple:
        """葉的一個槽 → (鍵, RID)。"""
        return self.key.decode(rec[_RID.size:]), _RID.unpack_from(rec, 0)

    def _inner_rec(self, sep: tuple, child: int) -> bytes:
        """(分隔項目, 子節點) → 內部節點的一個槽：子節點 4 bytes、RID 6 bytes，接著鍵的記錄。"""
        key, rid = sep
        rid = _LOW_RID_CODE if rid == LOW_RID else rid
        return _CHILD.pack(child) + _RID.pack(*rid) + self.key.encode(key)

    def _inner_entry(self, rec: bytes) -> tuple:
        """內部節點的一個槽 → (分隔項目, 子節點)；分隔項目是一個 (鍵, RID)。"""
        child = _CHILD.unpack_from(rec, 0)[0]
        rid = _RID.unpack_from(rec, _CHILD.size)
        rid = LOW_RID if rid == _LOW_RID_CODE else rid
        return (self.key.decode(rec[_CHILD.size + _RID.size:]), rid), child

    def _separator(self, left_last: bytes, right_first: bytes) -> tuple:
        """葉分裂後要「複製」到上一層的分隔項目：右半的第一個項目。
        左右兩邊的鍵不同時只取鍵，RID 記成 LOW_RID；找這個鍵時就直接走到右半，不必先讀左邊那一片葉。"""
        (left_key, _), (key, rid) = self._leaf_entry(left_last), self._leaf_entry(right_first)
        return (key, LOW_RID) if left_key < key else (key, rid)

    def _separator_of(self, rec: bytes) -> tuple:
        """內部節點的一個槽 → 它的分隔項目。"""
        return self._inner_entry(rec)[0]

    def _entries(self, node: SlottedPage) -> list:
        """節點的全部項目，依槽的次序解碼：葉是 (鍵, RID)，內部節點是 (分隔項目, 子節點)。"""
        decode = self._leaf_entry if node.kind == LEAF else self._inner_entry
        return [decode(node.get(i)) for i in range(node.n_slots)]

    def _records_from(self, leaf: SlottedPage, target) -> list[bytes]:
        """葉裡從第一個不小於 target 的項目開始的記錄（還沒解碼）；target 是 None 時從頭開始。"""
        start = 0 if target is None else bisect_left(_Sorted(leaf, self._leaf_entry), target)
        return [leaf.get(i) for i in range(start, leaf.n_slots)]

    def _visit(self, page_no: int):
        """讀一個節點 = 讀一頁。緊接著再讀同一頁（例如找到葉之後讀它的項目）不重複計算。"""
        if page_no != self._last_visit:
            self.visits += 1
            self._last_visit = page_no
        return self.pool.page(page_no)

    # ------------------------------------------------------------- 搜尋
    def _child_for(self, node: SlottedPage, target: tuple) -> int:
        """內部節點中 target 所在的子節點：小於或等於 target 的分隔項目有 i 個，就往 c_i 走。"""
        i = bisect_right(_Sorted(node, self._separator_of), target)
        return node.next if i == 0 else _CHILD.unpack_from(node.get(i - 1), 0)[0]

    def find_leaf(self, target: tuple) -> int:
        """演算法 FindLeaf：從根往下走到項目 target 所在（或應在）的葉，傳回葉的頁號。"""
        no, self._last_visit = self.root, None
        while True:
            with self._visit(no) as node:
                if node.kind == LEAF:
                    return no
                no = self._child_for(node, target)

    def _leftmost_leaf(self) -> int:
        """最左邊的葉：每一層都走第一個子節點 c_0，即 FindLeaf(T, −∞)。"""
        no, self._last_visit = self.root, None
        while True:
            with self._visit(no) as node:
                if node.kind == LEAF:
                    return no
                no = node.next

    def range(self, lo=None, hi=None, lo_inclusive=True, hi_inclusive=True):
        """演算法 RangeScan：依序產生鍵在 lo 與 hi 之間的 (鍵, RID)。

        lo、hi 是鍵的前綴（tuple），None 表示沒有這一側的界。例：索引鍵是 (room_id, start_at) 時，
        range((3,), (3,)) 是 room_id = 3 的所有項目；range((3, t), (3,)) 再加上 start_at ≥ t。
        """
        # 練習 U07-A：沿著葉鏈做範圍查詢 range（見本回的練習集）
        raise NotImplementedError("練習 U07-A：沿著葉鏈做範圍查詢 range")

    def search(self, key: tuple) -> list:
        """鍵等於 key 的所有 RID。"""
        return [rid for _, rid in self.range(tuple(key), tuple(key))]

    # ------------------------------------------------------------- 插入
    def insert(self, key: tuple, rid) -> None:
        """演算法 Insert：沿找葉的路徑放入 (key, rid)；節點放不下就分裂，分裂往上傳，根分裂時樹長高一層。"""
        key, rid = tuple(key), tuple(rid)
        if None in key:
            return                                   # NULL 不放進索引
        if len(self._inner_rec((key, rid), 0)) + SLOT > self.max_entry:
            raise ValueError(f"索引鍵太長：一個項目最多 {self.max_entry} bytes")
        self._last_visit = None
        split = self._insert(self.root, (key, rid))
        if split is None:
            return
        # 根分裂，樹長高一層。根的頁號不變：根現在的內容（分裂後的左半）搬到新的一頁，
        # 根改寫成只有兩個子節點的內部節點。
        sep, right = split
        f = self.pool.new_page(LEAF)                 # 種類不要緊：下一行把根的整頁（含種類）複製過來
        with self.pool.page(self.root, dirty=True) as root:
            f.data[:] = root.data
            root.data[:] = SlottedPage.new(INNER, len(root.data)).data
            root.next = f.page_no
            root.insert_at(0, self._inner_rec(sep, right))
        self.pool.unpin(f.page_no, dirty=True)

    def _insert(self, no: int, entry: tuple):
        """把 entry 放進以第 no 頁為根的子樹；這一頁分裂時傳回 (分隔項目, 新的右半頁號)。"""
        with self._visit(no) as node:
            child = None if node.kind == LEAF else self._child_for(node, entry)
        if child is None:
            with self.pool.page(no, dirty=True) as leaf:
                i = bisect_left(_Sorted(leaf, self._leaf_entry), entry)
                if i < leaf.n_slots and self._leaf_entry(leaf.get(i)) == entry:
                    return None                      # 已經在了
                rec = self._leaf_rec(*entry)
                if leaf.fits(rec):
                    leaf.insert_at(i, rec)
                    return None
                return self._split_leaf(leaf, i, rec)
        split = self._insert(child, entry)
        if split is None:
            return None
        sep, right = split
        with self.pool.page(no, dirty=True) as node:
            i = bisect_right(_Sorted(node, self._separator_of), sep)
            rec = self._inner_rec(sep, right)
            if node.fits(rec):
                node.insert_at(i, rec)
                return None
            return self._split_inner(node, i, rec)

    def _split_leaf(self, leaf: SlottedPage, i: int, rec: bytes):
        """葉分裂（演算法 Insert）：把 rec 放進第 i 個位置，前 m 筆留在原來的葉，其餘搬到新的葉；
        傳回 (分隔項目, 新的葉的頁號)，由上一層插入。"""
        recs = [leaf.get(k) for k in range(leaf.n_slots)]
        recs.insert(i, rec)
        m = _split_point(recs, 1, len(recs) - 1)
        # 練習 U07-B：葉分裂 _split_leaf（見本回的練習集）
        raise NotImplementedError("練習 U07-B：葉分裂 _split_leaf")

    def _split_inner(self, node: SlottedPage, i: int, rec: bytes):
        """內部節點分裂（演算法 Insert）：中間的分隔項目「搬」到上一層，
        它的子節點成為右半的最左子節點。"""
        recs = [node.get(k) for k in range(node.n_slots)]
        recs.insert(i, rec)
        m = _split_point(recs, 1, len(recs) - 2)
        up, up_child = self._inner_entry(recs[m])
        f = self.pool.new_page(INNER)
        right = SlottedPage(f.data)
        right.next = up_child
        node.clear()
        for k, r in enumerate(recs[:m]):
            node.insert_at(k, r)
        for k, r in enumerate(recs[m + 1:]):
            right.insert_at(k, r)
        self.pool.unpin(f.page_no, dirty=True)
        return up, f.page_no

    # ------------------------------------------------------------- 刪除
    def delete(self, key: tuple, rid) -> bool:
        """移除項目 (key, rid)，不合併節點。找到並移除時傳回 True。"""
        entry = (tuple(key), tuple(rid))
        if None in entry[0]:
            return False
        with self.pool.page(self.find_leaf(entry), dirty=True) as leaf:
            i = bisect_left(_Sorted(leaf, self._leaf_entry), entry)
            if i < leaf.n_slots and self._leaf_entry(leaf.get(i)) == entry:
                leaf.remove_at(i)
                return True
        return False

    # ------------------------------------------------------- 由下而上建樹
    @classmethod
    def build(cls, pool: BufferPool, key_schema: Schema, entries, fill: float = 0.9) -> int:
        """演算法 BulkLoad（bulk loading）：由依 (鍵, RID) 排好的項目，由下而上建一棵樹，傳回根的頁號。

        每一頁填到 fill 為止，就往右開新的一頁；葉層建好後，一層一層往上建內部節點，
        直到這一層只剩一個節點，它就是根。
        """
        if not 0.5 <= fill <= 1:
            raise ValueError("fill 要在 0.5 與 1 之間")
        tree = cls(pool, NONE, key_schema)
        limit = int(pool.pager.page_size * fill)
        level, f, leaf, prev = [], None, None, None  # level：[(這一頁的第一個項目, 頁號)]
        for key, rid in entries:
            entry = (tuple(key), tuple(rid))
            if None in entry[0]:
                continue
            if prev is not None and entry <= prev:
                if f is not None:
                    pool.unpin(f.page_no, dirty=True)
                raise ValueError("bulk loading 的項目必須依 (鍵, RID) 由小到大排好")
            if len(tree._inner_rec(entry, 0)) + SLOT > tree.max_entry:  # 與 insert 相同：分裂後兩半都放得下
                if f is not None:
                    pool.unpin(f.page_no, dirty=True)
                raise ValueError(f"索引鍵太長：一個項目最多 {tree.max_entry} bytes")
            rec = tree._leaf_rec(*entry)
            if leaf is None or _used(leaf) + len(rec) + SLOT > limit:
                new = pool.new_page(LEAF)
                if leaf is not None:
                    leaf.next = new.page_no
                    pool.unpin(f.page_no, dirty=True)
                f, leaf = new, SlottedPage(new.data)
                same_key = prev is not None and prev[0] == entry[0]
                level.append((entry if same_key else (entry[0], LOW_RID), f.page_no))
            leaf.insert_at(leaf.n_slots, rec)
            prev = entry
        if leaf is None:
            return cls.create(pool)
        pool.unpin(f.page_no, dirty=True)
        while len(level) > 1:                        # 每個節點：第一個子節點放在 next，其餘各佔一槽
            upper, f, node = [], None, None
            for first, child in level:
                rec = tree._inner_rec(first, child)
                if node is None or _used(node) + len(rec) + SLOT > limit:
                    if node is not None:
                        pool.unpin(f.page_no, dirty=True)
                    f = pool.new_page(INNER)
                    node = SlottedPage(f.data)
                    node.next = child
                    upper.append((first, f.page_no))
                else:
                    node.insert_at(node.n_slots, rec)
            pool.unpin(f.page_no, dirty=True)
            level = upper
        return level[0][1]

    # ------------------------------------------------------------- 檢查
    def check(self) -> list[str]:
        """檢查不變量，傳回發現的問題（空串列表示沒有問題）：
        節點內依序、子樹的項目落在分隔項目之間、所有葉同深度、葉鏈依序串起所有的葉。"""
        problems, depths, leaves = [], set(), []

        def walk(no, low, high, depth):
            with self.pool.page(no) as node:
                entries, kind, first_child = self._entries(node), node.kind, node.next
            items = entries if kind == LEAF else [sep for sep, _ in entries]
            if any(a >= b for a, b in zip(items, items[1:])):
                problems.append(f"第 {no} 頁的項目沒有由小到大")
            for x in items:
                if (low is not None and x < low) or (high is not None and x >= high):
                    problems.append(f"第 {no} 頁的 {x} 不在 [{low}, {high}) 之間")
            if kind == LEAF:
                depths.add(depth)
                leaves.append(no)
                return
            children = [first_child] + [c for _, c in entries]
            bounds = [low] + items + [high]
            for j, c in enumerate(children):
                walk(c, bounds[j], bounds[j + 1], depth + 1)

        walk(self.root, None, None, 0)
        if len(depths) > 1:
            problems.append(f"葉不在同一層：深度 {sorted(depths)}")
        chain, loop = self._leaf_chain(len(leaves))
        if loop:
            problems.append("葉鏈有環（某一片葉的 next 指回走過的葉）")
        elif chain != leaves:
            problems.append("葉鏈的順序與樹中由左到右的順序不同")
        return problems

    def _leaf_chain(self, limit: int) -> tuple[list, bool]:
        """沿著葉鏈走，傳回 (經過的頁號, 有沒有環)。回到走過的頁、或走了超過 limit 片，就停下來。"""
        chain, seen, no = [], set(), self._leftmost_leaf()
        while no != NONE:
            if no in seen or len(chain) > limit:
                return chain, True
            seen.add(no)
            chain.append(no)
            with self.pool.page(no) as leaf:
                no = leaf.next
        return chain, False

    def dump(self, show=None) -> str:
        """把樹一層一層畫成文字：每個節點是 [頁號: 鍵 ...]；內部節點列分隔項目的鍵，葉列項目的鍵。

        show(key) 決定一個鍵怎樣印（預設印第一欄）。最後一行是葉鏈的順序。"""
        show = show or (lambda key: str(key[0]) if len(key) == 1 else str(key))
        lines, level, depth, n_leaves = [], [self.root], 1, 0
        while level:
            nodes, below = [], []
            for no in level:
                with self.pool.page(no) as node:
                    entries, kind, first = self._entries(node), node.kind, node.next
                if kind == LEAF:
                    n_leaves += 1
                    nodes.append(f"[{no}: " + " ".join(show(k) for k, _ in entries) + "]")
                else:
                    nodes.append(f"[{no}: " + " ".join(show(k) for (k, _), _ in entries) + "]")
                    below += [first] + [c for _, c in entries]
            lines.append(f"第 {depth} 層  " + " ".join(nodes))
            level, depth = below, depth + 1
        chain, loop = self._leaf_chain(n_leaves)
        lines.append("葉鏈    " + " → ".join(str(no) for no in chain) + ("（有環）" if loop else ""))
        return "\n".join(lines)

    def height(self) -> int:
        """樹高 h：根到葉的路徑上的節點數。"""
        h, no = 1, self.root
        while True:
            with self.pool.page(no) as node:
                if node.kind == LEAF:
                    return h
                no, h = node.next, h + 1

    def stats(self) -> dict:
        """樹高、各層的節點數、項目數，與葉的平均填滿率。"""
        per_level, fills, n, level = [], [], 0, [self.root]
        while level:
            per_level.append(len(level))
            below = []
            for no in level:
                with self.pool.page(no) as node:
                    if node.kind == LEAF:
                        n += node.n_slots
                        fills.append(1 - (node.free_space() + node.holes()) / len(node.data))
                    else:
                        below += [node.next] + [c for _, c in self._entries(node)]
            level = below
        return {"height": len(per_level), "nodes_per_level": per_level, "entries": n,
                "leaf_fill": round(sum(fills) / len(fills), 3)}
