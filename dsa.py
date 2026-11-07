#!/usr/bin/env python3
"""Own data structures for the DSA project (no library containers inside).

- HashTable: open addressing with linear probing, power-of-two capacity,
  resize at load factor 0.7. Stores the banned-pair map of the draw.
- CircularList: circular doubly linked list used by the rotation draw.

The draw algorithms (draw_backtracking, draw_rotation) are pure functions,
so the Flask app and the benchmark drive the same code.
"""
from random import Random


# ---------------------------------------------------------------- hash table
class HashTable:
    """Key -> value with open addressing (linear probing).

    Values here are sets of banned receivers, keys are member ids.
    """

    _EMPTY = object()
    _DEAD = object()

    def __init__(self):
        self._cap = 8
        self._size = 0
        self._slots = [self._EMPTY] * self._cap

    def _idx(self, key):
        return hash(key) & (self._cap - 1)

    def set(self, key, value):
        if (self._size + 1) / self._cap > 0.7:
            self._resize(self._cap * 2)
        i = self._idx(key)
        while True:
            slot = self._slots[i]
            if slot is self._EMPTY or slot is self._DEAD:
                self._slots[i] = (key, value)
                self._size += 1
                return
            if slot[0] == key:
                self._slots[i] = (key, value)
                return
            i = (i + 1) & (self._cap - 1)

    def get(self, key, default=None):
        i = self._idx(key)
        while True:
            slot = self._slots[i]
            if slot is self._EMPTY:
                return default
            if slot is not self._DEAD and slot[0] == key:
                return slot[1]
            i = (i + 1) & (self._cap - 1)

    def has(self, key):
        return self.get(key, self._EMPTY) is not self._EMPTY

    def delete(self, key):
        i = self._idx(key)
        while True:
            slot = self._slots[i]
            if slot is self._EMPTY:
                return False
            if slot is not self._DEAD and slot[0] == key:
                self._slots[i] = self._DEAD
                self._size -= 1
                return True
            i = (i + 1) & (self._cap - 1)

    def keys(self):
        return [s[0] for s in self._slots if s is not self._EMPTY and s is not self._DEAD]

    def __len__(self):
        return self._size

    def _resize(self, cap):
        old = [s for s in self._slots if s is not self._EMPTY and s is not self._DEAD]
        self._cap, self._size, self._slots = cap, 0, [self._EMPTY] * cap
        for k, v in old:
            self.set(k, v)


# ------------------------------------------------------- circular linked list
class _Node:
    __slots__ = ("val", "prev", "next")

    def __init__(self, val):
        self.val = val
        self.prev = self.next = self


class CircularList:
    """Circular doubly linked list: O(1) step to the neighbour."""

    def __init__(self, items=()):
        self._tail = None
        self._n = 0
        for x in items:
            self.append(x)

    class Cursor:
        """A position in the circle."""

        def __init__(self, lst, node):
            self._lst = lst
            self._node = node

        @property
        def val(self):
            return self._node.val

        def next(self):
            self._node = self._node.next
            return self

    def append(self, val):
        node = _Node(val)
        if self._tail is None:
            node.prev = node.next = node
        else:
            t = self._tail
            node.prev, node.next = t, t.next
            t.next.prev = node
            t.next = node
        self._tail = node
        self._n += 1

    def cursor(self):
        if self._tail is None:
            return None
        return self.Cursor(self, self._tail)

    def __len__(self):
        return self._n


# ---------------------------------------------------------------- algorithms
def _as_table(mapping):
    t = HashTable()
    for k, v in mapping.items():
        t.set(k, v)
    return t


def fisher_yates(items, rng):
    """In-place uniform shuffle, O(n) time, O(1) extra space."""
    for i in range(len(items) - 1, 0, -1):
        j = rng.randrange(i + 1)
        items[i], items[j] = items[j], items[i]
    return items


def draw_backtracking(members, banned):
    """Full derangement honoring banned pairs by DFS with pruning.

    members: list of hashable ids; banned: HashTable id -> set of ids it
    must not gift (a member absent from the map bans nobody).
    Returns a list of (giver, receiver) pairs or None if no solution exists.
    Worst case O(n!) time, pruned heavily in practice; O(n) extra space.
    """
    banned = banned if isinstance(banned, HashTable) else _as_table(banned)
    # most restricted givers first: fail fast, prune early
    order = sorted(members, key=lambda u: len(banned.get(u, ()) or ()), reverse=True)
    taken = set()
    result = []

    def solve(i):
        if i == len(order):
            return True
        giver = order[i]
        forbidden = banned.get(giver, ())
        for receiver in members:
            if receiver == giver or receiver in taken or receiver in forbidden:
                continue
            taken.add(receiver)
            result.append((giver, receiver))
            if solve(i + 1):
                return True
            taken.discard(receiver)
            result.pop()
        return False

    return result if solve(0) else None


def draw_rotation(members, banned, rng, tries=50):
    """Rotation draw: shuffle members and seat them in a circle, each gifts
    the next one. O(n) per attempt; retries with a fresh shuffle while a
    banned pair sits in the circle. Returns pairs or None after `tries`.
    """
    banned = banned if isinstance(banned, HashTable) else _as_table(banned)
    ring = list(members)
    for _ in range(tries):
        fisher_yates(ring, rng)
        circle = CircularList(ring)
        pairs, cur = [], circle.cursor()
        ok = len(circle) >= 2
        for _ in range(len(circle)):
            giver = cur.val
            nxt = cur.next().val
            forbidden = banned.get(giver, ())
            if giver == nxt or nxt in forbidden:
                ok = False
                break
            pairs.append((giver, nxt))
        if ok:
            return pairs
    return None
