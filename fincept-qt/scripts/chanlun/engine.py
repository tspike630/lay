# -*- coding: utf-8 -*-
"""Local Chanlun (缠论) structure engine.

bbfamily/abu documents 缠论一买/二买/三买 on abuquant.com, but the open-source
tree has no chanlun implementation. This module is an original reading of the
public 缠中说禅 rules (inclusion, fractals, bi, segments, zhongshu, and the
three buy/sell points with MACD area divergence). It does not call Fincept or
abu servers.

Stdlib only, so the terminal can run it with the bundled Python.
"""

from __future__ import absolute_import

import math


def _bar(raw, idx):
    high = float(raw["h"] if "h" in raw else raw["high"])
    low = float(raw["l"] if "l" in raw else raw["low"])
    close = float(raw["c"] if "c" in raw else raw["close"])
    open_ = float(raw["o"] if "o" in raw else raw.get("open", close))
    if high < low:
        high, low = low, high
    return {
        "o": open_,
        "h": high,
        "l": low,
        "c": close,
        "raw_start": idx,
        "raw_end": idx,
        "t": raw.get("t") or raw.get("date") or str(idx),
    }


def _contains(outer, inner):
    return outer["h"] >= inner["h"] and outer["l"] <= inner["l"]


def merge_klines(bars):
    """处理包含关系. 向上取高高、低高；向下取高低、低低."""
    merged = []
    direction = 1
    for i, raw in enumerate(bars):
        cur = _bar(raw, i)
        if not merged:
            merged.append(cur)
            continue
        prev = merged[-1]
        if _contains(prev, cur) or _contains(cur, prev):
            if direction >= 0:
                prev["h"] = max(prev["h"], cur["h"])
                prev["l"] = max(prev["l"], cur["l"])
            else:
                prev["h"] = min(prev["h"], cur["h"])
                prev["l"] = min(prev["l"], cur["l"])
            if prev["h"] < prev["l"]:
                prev["h"], prev["l"] = prev["l"], prev["h"]
            prev["c"] = cur["c"]
            prev["raw_end"] = i
        else:
            direction = 1 if cur["h"] >= prev["h"] else -1
            merged.append(cur)
    return merged


def find_fractals(merged):
    """顶分型 / 底分型. 中间 K 的高低点都严格高于或低于左右."""
    out = []
    for i in range(1, len(merged) - 1):
        left, mid, right = merged[i - 1], merged[i], merged[i + 1]
        is_top = (
            mid["h"] > left["h"]
            and mid["h"] > right["h"]
            and mid["l"] > left["l"]
            and mid["l"] > right["l"]
        )
        is_bottom = (
            mid["l"] < left["l"]
            and mid["l"] < right["l"]
            and mid["h"] < left["h"]
            and mid["h"] < right["h"]
        )
        if is_top:
            out.append({"type": "top", "midx": i, "price": mid["h"], "raw": mid["raw_end"]})
        elif is_bottom:
            out.append({"type": "bottom", "midx": i, "price": mid["l"], "raw": mid["raw_start"]})
    return out


def find_bi(fractals):
    """新笔: 顶底交替，合并 K 下标至少隔 4 根（中间有独立 K）."""
    if not fractals:
        return []
    seq = [fractals[0]]
    for fx in fractals[1:]:
        last = seq[-1]
        if fx["type"] == last["type"]:
            if fx["type"] == "top" and fx["price"] >= last["price"]:
                seq[-1] = fx
            elif fx["type"] == "bottom" and fx["price"] <= last["price"]:
                seq[-1] = fx
            continue
        if fx["midx"] - last["midx"] < 4:
            continue
        if last["type"] == "bottom" and fx["price"] <= last["price"]:
            continue
        if last["type"] == "top" and fx["price"] >= last["price"]:
            continue
        seq.append(fx)
    bis = []
    for i in range(len(seq) - 1):
        a, b = seq[i], seq[i + 1]
        direction = "up" if a["type"] == "bottom" else "down"
        bis.append(
            {
                "direction": direction,
                "start": int(a["raw"]),
                "end": int(b["raw"]),
                "start_price": a["price"],
                "end_price": b["price"],
                "high": max(a["price"], b["price"]),
                "low": min(a["price"], b["price"]),
            }
        )
    return bis


def _feature_fractal(direction, a, b, c):
    if direction == "up":
        return b["high"] > a["high"] and b["high"] > c["high"] and b["low"] > a["low"] and b["low"] > c["low"]
    return b["low"] < a["low"] and b["low"] < c["low"] and b["high"] < a["high"] and b["high"] < c["high"]


def find_segments(bis):
    """线段: 至少三笔. 反向笔组成特征序列，出现分型则线段结束."""
    segments = []
    i = 0
    n = len(bis)
    while i <= n - 3:
        direction = bis[i]["direction"]
        feats = []
        ended = None
        j = i
        while j < n:
            if bis[j]["direction"] != direction:
                feats.append(j)
                if len(feats) >= 3:
                    a, b, c = feats[-3], feats[-2], feats[-1]
                    if _feature_fractal(direction, bis[a], bis[b], bis[c]):
                        candidate = b - 1
                        if candidate >= i + 2:
                            ended = candidate
                            break
            j += 1
        if ended is None:
            ended = n - 1
            if ended - i < 2:
                break
        chunk = bis[i : ended + 1]
        segments.append(
            {
                "direction": direction,
                "start": chunk[0]["start"],
                "end": chunk[-1]["end"],
                "high": max(item["high"] for item in chunk),
                "low": min(item["low"] for item in chunk),
                "bi_from": i,
                "bi_to": ended,
            }
        )
        i = ended + 1
    return segments


def find_zhongshu(bis):
    """笔中枢: 连续三笔重叠区间 [ZD, ZG]，之后的笔仍与该区间重叠则延伸."""
    pivots = []
    i = 0
    while i + 2 < len(bis):
        window = bis[i : i + 3]
        zg = min(item["high"] for item in window)
        zd = max(item["low"] for item in window)
        if zg <= zd:
            i += 1
            continue
        end = i + 2
        k = i + 3
        while k < len(bis):
            item = bis[k]
            if item["high"] < zd or item["low"] > zg:
                break
            end = k
            k += 1
        chunk = bis[i : end + 1]
        pivots.append(
            {
                "zd": zd,
                "zg": zg,
                "gg": max(item["high"] for item in chunk),
                "dd": min(item["low"] for item in chunk),
                "start": chunk[0]["start"],
                "end": chunk[-1]["end"],
                "bi_from": i,
                "bi_to": end,
            }
        )
        i = end + 1
    return pivots


def _ema(values, period):
    if not values:
        return []
    k = 2.0 / (period + 1.0)
    prev = values[0]
    out = []
    for value in values:
        prev = value * k + prev * (1.0 - k)
        out.append(prev)
    return out


def macd_hist(closes):
    if len(closes) < 2:
        return [0.0 for _ in closes]
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif = [a - b for a, b in zip(ema12, ema26)]
    dea = _ema(dif, 9)
    return [(d - e) * 2.0 for d, e in zip(dif, dea)]


def _area(hist, start, end):
    if not hist:
        return 0.0
    a = max(0, min(start, end))
    b = min(len(hist) - 1, max(start, end))
    return sum(hist[a : b + 1])


def find_signals(bis, pivots, hist):
    """一买/一卖看离开中枢后的 MACD 柱面积背驰；二买/二卖是回抽不破；三买/三卖是回抽不进中枢."""
    signals = []
    down = [idx for idx, bi in enumerate(bis) if bi["direction"] == "down"]
    up = [idx for idx, bi in enumerate(bis) if bi["direction"] == "up"]

    def add(kind, bi_index, reason):
        bi = bis[bi_index]
        signals.append(
            {
                "type": kind,
                "index": int(bi["end"]),
                "price": bi["end_price"],
                "reason": reason,
            }
        )

    for pivot in pivots:
        # The first three bi define the pivot. Later bi that still overlap extend
        # it, but a leave-and-divergence can sit inside that extension.
        core_end = pivot["bi_from"] + 2
        after = [idx for idx in down if idx > core_end and bis[idx]["low"] < pivot["zd"]]
        for pos, idx in enumerate(after):
            prev_idx = None
            for earlier in reversed(down):
                if earlier < idx:
                    prev_idx = earlier
                    break
            if prev_idx is None:
                continue
            cur, prev = bis[idx], bis[prev_idx]
            if cur["low"] < prev["low"] and abs(_area(hist, cur["start"], cur["end"])) < abs(
                _area(hist, prev["start"], prev["end"])
            ):
                add("buy1", idx, "向下离开中枢后创新低，MACD 柱面积未创新低")
                nxt = None
                for later in down:
                    if later > idx:
                        nxt = later
                        break
                if nxt is not None and bis[nxt]["low"] > cur["low"]:
                    add("buy2", nxt, "一买之后的回抽低点高于一买")
                break

        leave_up = [idx for idx in up if idx > core_end and bis[idx]["high"] > pivot["zg"]]
        if leave_up:
            leave = leave_up[0]
            for idx in down:
                if idx > leave and bis[idx]["low"] > pivot["zg"]:
                    add("buy3", idx, "向上离开中枢后的回抽低点不进中枢")
                    break

        after_up = [idx for idx in up if idx > core_end and bis[idx]["high"] > pivot["zg"]]
        for idx in after_up:
            prev_idx = None
            for earlier in reversed(up):
                if earlier < idx:
                    prev_idx = earlier
                    break
            if prev_idx is None:
                continue
            cur, prev = bis[idx], bis[prev_idx]
            if cur["high"] > prev["high"] and abs(_area(hist, cur["start"], cur["end"])) < abs(
                _area(hist, prev["start"], prev["end"])
            ):
                add("sell1", idx, "向上离开中枢后创新高，MACD 柱面积未创新高")
                nxt = None
                for later in up:
                    if later > idx:
                        nxt = later
                        break
                if nxt is not None and bis[nxt]["high"] < cur["high"]:
                    add("sell2", nxt, "一卖之后的反弹高点低于一卖")
                break

        leave_dn = [idx for idx in down if idx > core_end and bis[idx]["low"] < pivot["zd"]]
        if leave_dn:
            leave = leave_dn[0]
            for idx in up:
                if idx > leave and bis[idx]["high"] < pivot["zd"]:
                    add("sell3", idx, "向下离开中枢后的反弹高点不进中枢")
                    break

    deduped = []
    seen = set()
    for sig in signals:
        key = (sig["type"], sig["index"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(sig)
    deduped.sort(key=lambda item: (item["index"], item["type"]))
    return deduped


def analyze(bars):
    cleaned = []
    for raw in bars:
        try:
            cleaned.append(raw)
            _bar(raw, len(cleaned) - 1)
        except (TypeError, ValueError, KeyError):
            cleaned.pop()
    merged = merge_klines(cleaned)
    fractals = find_fractals(merged)
    bis = find_bi(fractals)
    segments = find_segments(bis)
    pivots = find_zhongshu(bis)
    closes = []
    for i, raw in enumerate(cleaned):
        closes.append(_bar(raw, i)["c"])
    hist = macd_hist(closes)
    signals = find_signals(bis, pivots, hist)
    names = {
        "buy1": "一买",
        "buy2": "二买",
        "buy3": "三买",
        "sell1": "一卖",
        "sell2": "二卖",
        "sell3": "三卖",
    }
    last = signals[-1] if signals else None
    if last:
        summary = "最近信号：{0} @ {1:.4f}（第 {2} 根）".format(
            names.get(last["type"], last["type"]), last["price"], last["index"] + 1
        )
    else:
        summary = "已画出笔和中枢，当前没有满足背驰或回抽条件的买卖点"
    return {
        "count": len(cleaned),
        "merged_count": len(merged),
        "fractal_count": len(fractals),
        "bi": bis,
        "segments": segments,
        "zhongshu": pivots,
        "signals": signals,
        "summary": summary,
        "bars": [
            {
                "i": i,
                "t": _bar(raw, i)["t"],
                "o": _bar(raw, i)["o"],
                "h": _bar(raw, i)["h"],
                "l": _bar(raw, i)["l"],
                "c": _bar(raw, i)["c"],
            }
            for i, raw in enumerate(cleaned)
        ],
    }


def sample_bars():
    """确定性样本，方便没有行情文件时直接看结构."""
    bars = []
    price = 100.0
    for i in range(220):
        if i < 50:
            drift = 0.45
        elif i < 110:
            drift = 0.8 * math.sin(i / 4.0)
        elif i < 160:
            drift = -0.55
        elif i < 190:
            drift = 0.25
        else:
            drift = -0.15
        wave = math.sin(i / 2.5)
        price = max(8.0, price + drift * 0.15 + wave * 0.35)
        span = 0.9 + 0.25 * abs(math.sin(i / 3.0))
        bars.append(
            {
                "t": "S{0:03d}".format(i),
                "o": price - 0.15,
                "h": price + span,
                "l": price - span,
                "c": price + 0.1 * wave,
            }
        )
    return bars


def _self_check():
    zigzag = []
    mids = [10, 12, 15, 13, 11, 8, 6, 8, 11, 14, 12, 9, 7, 9, 12, 16, 13, 10]
    for i, mid in enumerate(mids):
        # Widen each bar so neighbours are not inclusive and fractals can form.
        span = 0.6 + (i % 3) * 0.05
        zigzag.append({"h": mid + span + 0.4, "l": mid - span, "c": mid, "o": mid})
    result = analyze(zigzag)
    assert result["fractal_count"] >= 1, result
    sample = analyze(sample_bars())
    assert sample["count"] == 220
    assert sample["bi"], sample["summary"]
    assert sample["zhongshu"], sample
    assert sample["signals"], sample["summary"]
    for sig in sample["signals"]:
        assert sig["type"] in ("buy1", "buy2", "buy3", "sell1", "sell2", "sell3")
    return sample["summary"]


if __name__ == "__main__":
    print(_self_check())
