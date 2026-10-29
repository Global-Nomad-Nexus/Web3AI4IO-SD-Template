"""Draw the four figures for the 7-day cohort progress note."""

import csv
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont

BASE = Path("/work/so192/scientific data/data/7day-72h-20261008T000000Z")
OUT = Path("/work/so192/scientific data/7day+72h/figures")
FONT_CJK = "/usr/share/fonts/google-droid-sans-fonts/DroidSansFallbackFull.ttf"
FONT_LATIN = "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf"
BJ = timezone(timedelta(hours=8))

INK = (28, 28, 28)
MUTED = (90, 90, 90)
BLUE = (31, 78, 121)
GRAY = (168, 164, 156)
GRID = (226, 226, 226)
WHITE = (255, 255, 255)


def font_for(ch, size):
    path = FONT_LATIN if ord(ch) < 128 else FONT_CJK
    return ImageFont.truetype(path, size)


def text_size(draw, text, size):
    width = 0
    height = 0
    for ch in text:
        box = draw.textbbox((0, 0), ch, font=font_for(ch, size))
        width += box[2] - box[0]
        height = max(height, box[3] - box[1])
    return width, height


def draw_text(draw, xy, text, size, fill, align="left", valign="top"):
    width, height = text_size(draw, text, size)
    x, y = xy
    if align == "right":
        x -= width
    elif align == "center":
        x -= width / 2
    if valign == "middle":
        y -= height / 2
    elif valign == "bottom":
        y -= height
    ascent = max(font_for("A", size).getmetrics()[0], font_for("中", size).getmetrics()[0])
    baseline = y + ascent
    for ch in text:
        face = font_for(ch, size)
        draw.text((x, baseline), ch, font=face, fill=fill, anchor="ls")
        box = draw.textbbox((0, 0), ch, font=face)
        x += box[2] - box[0]


def comma(n):
    return f"{n:,}"


def load():
    days = Counter()
    declared = Counter()
    mints, creators = set(), set()
    bt_min = bt_max = None
    with (BASE / "run/launch_events.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            bt = int(row["block_time"])
            bt_min = bt if bt_min is None else min(bt_min, bt)
            bt_max = bt if bt_max is None else max(bt_max, bt)
            day = datetime.fromtimestamp(bt, timezone.utc).strftime("%m-%d")
            days[day] += 1
            mints.add(row["mint"])
            creators.add(row["creator"])
            uri = row["metadata_uri"] or ""
            parsed = urlparse(uri)
            declared[bucket_declared(parsed.netloc, parsed.scheme, uri)] += 1

    final = Counter()
    by_cp = {}
    late = Counter()
    for cp in ("T0", "T24", "T48", "T72"):
        by_cp[cp] = Counter()
    with (BASE / "run/coverage_ledger.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            final[row["final_state"]] += 1
            by_cp[row["checkpoint"]][row["final_state"]] += 1
            if row["timing_state"] == "late":
                late[row["checkpoint"]] += 1

    hosts = Counter()
    snap_parse = Counter()
    with (BASE / "run/response_snapshots.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            hosts[urlparse(row["request_url"]).netloc] += 1
            snap_parse[row["parse_state"]] += 1

    presence = Counter()
    with (BASE / "run/field_observations.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            presence[row["field_name"] + "|" + row["presence"]] += 1

    return {
        "days": days,
        "declared": declared,
        "events": sum(days.values()),
        "mints": len(mints),
        "creators": len(creators),
        "bt_min": datetime.fromtimestamp(bt_min, BJ).strftime("%Y-%m-%d %H:%M:%S"),
        "bt_max": datetime.fromtimestamp(bt_max, BJ).strftime("%Y-%m-%d %H:%M:%S"),
        "final": final,
        "by_cp": {k: dict(v) for k, v in by_cp.items()},
        "late": late,
        "hosts": hosts,
        "snap_parse": snap_parse,
        "presence": presence,
    }


def bucket_declared(host, scheme, uri):
    h = (host or "").lower()
    if h == "ipfs.io":
        return "ipfs.io"
    if h == "metadata.j7tracker.io":
        return "metadata.j7tracker.io"
    if h == "meta.uxento.io":
        return "meta.uxento.io"
    if h == "m.rapidlaunch.io":
        return "m.rapidlaunch.io"
    ipfsish = (
        scheme == "ipfs"
        or "pinata" in h
        or "ipfs" in h
        or h.endswith(".ipfs.inbrowser.link")
        or (not h and (uri.startswith("Qm") or uri.startswith("baf")))
    )
    if ipfsish:
        return "其他 IPFS / Pinata"
    if "arweave" in h or h == "gateway.irys.xyz" or scheme == "ar":
        return "Arweave / Irys"
    if not h:
        return "裸 CID"
    return "其他 HTTPS"


def new_canvas(w, h):
    image = Image.new("RGB", (w, h), WHITE)
    return image, ImageDraw.Draw(image)


def vline_grid(draw, x0, x1, y, ticks, y_of):
    for tick in ticks:
        y_pos = y_of(tick)
        draw.line((x0, y_pos, x1, y_pos), fill=GRID, width=1)


def draw_daily(stats):
    w, h = 1500, 860
    image, draw = new_canvas(w, h)
    title_f = font(34)
    axis_f = font(22)
    tick_f = font(20)
    label_f = font(20)
    draw.text((70, 28), "每天纳入的创建", font=title_f, fill=INK)

    days = [f"10-{d:02d}" for d in range(8, 15)]
    keys = [f"10-{d:02d}"[3:] if False else f"{d:02d}" for d in range(8, 15)]
    # keys in the counter are mm-dd with month 10
    keys = [f"10-{d:02d}" for d in range(8, 15)]
    values = [stats["days"][k] for k in keys]
    assert sum(values) == stats["events"]

    left, right, top, bottom = 100, 40, 110, 90
    plot_w, plot_h = w - left - right, h - top - bottom
    y_max = 1500

    def y_of(value):
        return top + plot_h - (value / y_max) * plot_h

    vline_grid(draw, left, w - right, 0, (0, 300, 600, 900, 1200, 1500), y_of)
    draw.line((left, top, left, top + plot_h), fill=INK, width=2)
    draw.line((left, top + plot_h, w - right, top + plot_h), fill=INK, width=2)

    for tick in (0, 300, 600, 900, 1200, 1500):
        y_pos = y_of(tick)
        label = comma(tick)
        tw, th = text_size(draw, label, tick_f)
        draw.text((left - tw - 12, y_pos - th / 2), label, font=tick_f, fill=MUTED)

    gap = plot_w / len(values)
    bar_w = 78
    for i, (key, value) in enumerate(zip(keys, values)):
        cx = left + gap * (i + 0.5)
        x0 = cx - bar_w / 2
        y0 = y_of(value)
        y1 = top + plot_h
        draw.rectangle((x0, y0, x0 + bar_w, y1), fill=BLUE)
        value_label = comma(value)
        tw, th = text_size(draw, value_label, label_f)
        draw.text((cx - tw / 2, y0 - th - 10), value_label, font=label_f, fill=INK)
        day_label = key[3:] + "日"
        tw, th = text_size(draw, day_label, axis_f)
        draw.text((cx - tw / 2, top + plot_h + 16), day_label, font=axis_f, fill=INK)

    ylab = "创建（笔）"
    tw, th = text_size(draw, ylab, axis_f)
    draw.text((left, top - th - 12), ylab, font=axis_f, fill=MUTED)
    xlab = "10 月，UTC 日"
    tw, th = text_size(draw, xlab, axis_f)
    draw.text((w - right - tw, h - 36), xlab, font=axis_f, fill=MUTED)
    image.save(OUT / "daily.png")


def draw_checkpoints(stats):
    w, h = 1500, 900
    image, draw = new_canvas(w, h)
    title_f = font(34)
    axis_f = font(22)
    tick_f = font(20)
    label_f = font(20)
    draw.text((70, 28), "四个观察点的终态", font=title_f, fill=INK)

    order = ["T0", "T24", "T48", "T72"]
    left, right, top, bottom = 110, 40, 150, 80
    plot_w, plot_h = w - left - right, h - top - bottom
    y_max = 5000

    def y_of(value):
        return top + plot_h - (value / y_max) * plot_h

    vline_grid(draw, left, w - right, 0, (0, 1000, 2000, 3000, 4000, 5000), y_of)
    draw.line((left, top, left, top + plot_h), fill=INK, width=2)
    draw.line((left, top + plot_h, w - right, top + plot_h), fill=INK, width=2)
    for tick in (0, 1000, 2000, 3000, 4000, 5000):
        y_pos = y_of(tick)
        label = comma(tick)
        tw, th = text_size(draw, label, tick_f)
        draw.text((left - tw - 12, y_pos - th / 2), label, font=tick_f, fill=MUTED)

    gap = plot_w / len(order)
    bar_w = 110
    for i, cp in enumerate(order):
        counts = stats["by_cp"][cp]
        ok = counts.get("observed", 0)
        failed = counts.get("request_failed", 0)
        cx = left + gap * (i + 0.5)
        x0 = cx - bar_w / 2
        y_fail_top = y_of(ok + failed)
        y_ok_top = y_of(ok)
        y_base = top + plot_h
        draw.rectangle((x0, y_ok_top, x0 + bar_w, y_base), fill=BLUE)
        draw.rectangle((x0, y_fail_top, x0 + bar_w, y_ok_top), fill=GRAY)
        fail_label = comma(failed)
        tw, th = text_size(draw, fail_label, label_f)
        draw.text((cx - tw / 2, y_fail_top - th - 8), fail_label, font=label_f, fill=INK)
        ok_label = comma(ok)
        tw, th = text_size(draw, ok_label, label_f)
        draw.text((cx - tw / 2, y_ok_top + 16), ok_label, font=label_f, fill=WHITE)
        tw, th = text_size(draw, cp, axis_f)
        draw.text((cx - tw / 2, top + plot_h + 16), cp, font=axis_f, fill=INK)

    legend_y = 86
    draw.rectangle((70, legend_y, 96, legend_y + 22), fill=BLUE)
    draw.text((106, legend_y - 2), "成功解析", font=axis_f, fill=INK)
    draw.rectangle((250, legend_y, 276, legend_y + 22), fill=GRAY)
    draw.text((286, legend_y - 2), "请求失败（柱顶数字）", font=axis_f, fill=INK)
    image.save(OUT / "checkpoints.png")


def hbars(draw, origin, size, rows, x_max, ticks, value_font, label_font, tick_font):
    x, y = origin
    width, height = size
    n = len(rows)
    band = height / n

    def x_of(value):
        return x + (value / x_max) * width

    for tick in ticks:
        x_pos = x_of(tick)
        draw.line((x_pos, y, x_pos, y + height), fill=GRID, width=1)
    draw.line((x, y, x, y + height), fill=INK, width=2)
    draw.line((x, y + height, x + width, y + height), fill=INK, width=2)

    for tick in ticks:
        label = comma(tick)
        tw, th = text_size(draw, label, tick_font)
        x_pos = x_of(tick)
        draw.text((x_pos - tw / 2, y + height + 10), label, font=tick_font, fill=MUTED)

    for i, (label, value) in enumerate(rows):
        cy = y + band * (i + 0.5)
        bar_h = min(36, band * 0.62)
        y0 = cy - bar_h / 2
        x1 = x_of(value)
        draw.rectangle((x, y0, x1, y0 + bar_h), fill=BLUE)
        tw, th = text_size(draw, label, label_font)
        draw.text((x - tw - 14, cy - th / 2), label, font=label_font, fill=INK)
        value_label = comma(value)
        tw, th = text_size(draw, value_label, value_font)
        if x1 - x > tw + 24:
            draw.text((x1 - tw - 10, cy - th / 2), value_label, font=value_font, fill=WHITE)
        else:
            draw.text((x1 + 8, cy - th / 2), value_label, font=value_font, fill=INK)


def draw_sources(stats):
    w, h = 1700, 980
    image, draw = new_canvas(w, h)
    title_f = font(34)
    head_f = font(24)
    label_f = font(20)
    tick_f = font(18)
    draw.text((40, 24), "元数据从哪里来", font=title_f, fill=INK)

    declared_order = [
        "ipfs.io",
        "metadata.j7tracker.io",
        "其他 HTTPS",
        "其他 IPFS / Pinata",
        "meta.uxento.io",
        "m.rapidlaunch.io",
        "Arweave / Irys",
        "裸 CID",
    ]
    # Merge the two tiny tails so the axis stays readable, but keep the count.
    tiny = stats["declared"]["Arweave / Irys"] + stats["declared"]["裸 CID"]
    left_rows = [(name, stats["declared"][name]) for name in declared_order if name not in ("Arweave / Irys", "裸 CID")]
    left_rows.append(("Arweave / Irys、裸 CID", tiny))
    left_rows.sort(key=lambda item: item[1], reverse=True)

    keep = {
        "pump.mypinata.cloud",
        "metadata.j7tracker.io",
        "meta.uxento.io",
        "m.rapidlaunch.io",
    }
    right_counter = Counter()
    for host, count in stats["hosts"].items():
        right_counter[host if host in keep else "其他主机"] += count
    right_rows = right_counter.most_common()

    draw.text((70, 86), "创建交易里写的地址", font=head_f, fill=INK)
    draw.text((930, 86), "成功取回时访问的主机", font=head_f, fill=INK)
    sub_f = font(18)
    draw.text((70, 122), f"按创建计，{comma(stats['events'])} 笔", font=sub_f, fill=MUTED)
    draw.text((930, 122), f"按响应快照计，{comma(sum(stats['hosts'].values()))} 次", font=sub_f, fill=MUTED)

    hbars(
        draw,
        (300, 180),
        (500, 700),
        left_rows,
        4000,
        (0, 1000, 2000, 3000, 4000),
        label_f,
        label_f,
        tick_f,
    )
    hbars(
        draw,
        (1180, 180),
        (460, 700),
        right_rows,
        14000,
        (0, 4000, 8000, 12000),
        label_f,
        label_f,
        tick_f,
    )
    image.save(OUT / "sources.png")
    return left_rows, right_rows


def draw_fields(stats):
    w, h = 1500, 860
    image, draw = new_canvas(w, h)
    title_f = font(34)
    label_f = font(22)
    tick_f = font(18)
    draw.text((40, 28), "解析成功的记录里，字段是否有值", font=title_f, fill=INK)
    fields = ["name", "symbol", "description", "createdOn", "image", "website", "twitter", "telegram"]
    rows = []
    for name in fields:
        present = stats["presence"][name + "|present"]
        rows.append((name, present))
    denom = rows[0][1]
    # name is always present in this run; still use observed count from the ledger via name.
    sub_f = font(20)
    draw.text((40, 78), f"分母是成功解析的 {comma(denom)} 条观察", font=sub_f, fill=MUTED)

    left, top = 180, 140
    plot_w, plot_h = 1080, 620
    hbars(
        draw,
        (left, top),
        (plot_w, plot_h),
        rows,
        16736,
        (0, 4000, 8000, 12000, 16000),
        label_f,
        label_f,
        tick_f,
    )
    image.save(OUT / "fields.png")
    return rows


def main():
    stats = load()
    draw_daily(stats)
    draw_checkpoints(stats)
    left_rows, right_rows = draw_sources(stats)
    field_rows = draw_fields(stats)
    printable = {
        "events": stats["events"],
        "mints": stats["mints"],
        "creators": stats["creators"],
        "bt_min": stats["bt_min"],
        "bt_max": stats["bt_max"],
        "days": dict(sorted(stats["days"].items())),
        "final": stats["final"],
        "by_cp": stats["by_cp"],
        "late": dict(stats["late"]),
        "declared": dict(stats["declared"]),
        "left_rows": left_rows,
        "right_rows": right_rows,
        "snap_parse": dict(stats["snap_parse"]),
        "snapshots": sum(stats["hosts"].values()),
        "field_rows": field_rows,
    }
    print(json.dumps(printable, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
