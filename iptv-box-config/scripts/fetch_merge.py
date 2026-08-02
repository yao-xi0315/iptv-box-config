#!/usr/bin/env python3
"""
fetch_merge.py
==============
每天自动执行：
  1. 从多个公网源拉取 m3u 直播源（带重试 + UA 轮换）
  2. HEAD 测存活 + ffprobe 抽帧测速
  3. 与仓库内 my_tvbox.json 的静态源合并去重
  4. 输出新的 my_tvbox.json + output/merged.m3u

设计原则：
  - 单条源失败不影响其他源（容错）
  - 全部抓取失败时用上一次 lives 兜底（保证盒子不断源）
  - 在 GitHub Actions runner 上运行（有正常公网），本地仅作测试
"""

import json
import os
import time
import random
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# ===================== 日志 =====================
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.info
warn = logging.warning

# ===================== 配置区 =====================

# UA 池，随机切换避免被 ban
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "VLC/3.0.20 LibVLC/3.0.20",
    "IPTV-Client/1.0",
]

def get_headers(referer=None):
    h = {
        "User-Agent": random.choice(UA_POOL),
        "Accept": "*/*",
        "Connection": "close",
    }
    if referer:
        h["Referer"] = referer
    return h

# 要抓取的公网源
PUBLIC_SOURCES = [
    {"name": "fanmingming_ipv6", "url": "https://live.fanmingming.cn/tv/m3u/ipv6.m3u", "timeout": 20},
    {"name": "fanmingming_ipv4", "url": "https://live.fanmingming.cn/tv/m3u/iptv4.m3u", "timeout": 20},
    {"name": "zbds_ipv4",       "url": "https://live.zbds.top/tv/iptv4.m3u", "timeout": 20},
    {"name": "bestfan_cctv",    "url": "https://gh-proxy.com/https://raw.githubusercontent.com/best-fan/iptv-sources/master/cn_cctv.m3u8", "timeout": 25},
    {"name": "bestfan_all",     "url": "https://gh-proxy.com/https://raw.githubusercontent.com/best-fan/iptv-sources/master/cn_all.m3u8", "timeout": 25},
    {"name": "kimentanm",      "url": "https://gh.927223.xyz/https://raw.githubusercontent.com/Kimentanm/aptv/master/m3u/iptv.m3u", "timeout": 25},
    {"name": "cs3306",          "url": "https://raw.githubusercontent.com/cs3306/IPTV-Sources/main/data/output/iptv_collection.m3u", "timeout": 25},
    {"name": "guovin_ipv4",    "url": "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv4/result.m3u", "timeout": 25},
    {"name": "10000ge10000",   "url": "https://raw.githubusercontent.com/10000ge10000/iptv-api/refs/heads/master/output/user_result.m3u", "timeout": 25},
]

# 静态影视源（不参与抓取，永远保留）
STATIC_SITES = [
    {"key": "fan",     "name": "饭太硬（主源）", "type": 3, "api": "https://qist.wyfc.qzz.io/fty.json",       "searchable": 1, "quickSearch": 1, "changeable": 1},
    {"key": "jundie",  "name": "俊于（备源）",   "type": 3, "api": "http://home.jundie.top:81/top98.json",  "searchable": 1, "quickSearch": 1, "changeable": 1},
    {"key": "tvbox2h", "name": "2hacc 主接口",    "type": 3, "api": "https://raw.iqiq.io/2hacc/TVBox/main/tvbox.json", "searchable": 1, "quickSearch": 1, "changeable": 1},
    {"key": "wzh15802","name": "wzh 多仓",        "type": 3, "api": "https://gh-proxy.com/https://raw.githubusercontent.com/wzh15802/tvbox/main/tv.json", "searchable": 1, "quickSearch": 1, "changeable": 1},
    {"key": "liucn",   "name": "liucn 通用仓",    "type": 3, "api": "https://raw.liucn.cc/box/m.json",       "searchable": 1, "quickSearch": 1, "changeable": 1},
]

TOP_N_LIVE   = 40   # 最终保留最快源数量
PROBE_LIMIT  = 20   # ffprobe 深度探测上限
CONCURRENCY  = 10   # 并发测速线程数
RETRY        = 2    # 每个源最多重试次数

# ===================== 工具函数 =====================

def fetch_text(url, timeout=20):
    """下载文本，带重试和 UA 轮换"""
    last_err = ""
    for attempt in range(1, RETRY + 1):
        try:
            r = requests.get(url, headers=get_headers(), timeout=timeout, allow_redirects=True)
            if r.status_code == 200 and len(r.text) > 100:
                return r.text
            last_err = f"HTTP {r.status_code}"
        except Exception as e:
            last_err = str(e)
        warn(f"  重试 {attempt}/{RETRY} -> {last_err}")
        time.sleep(2 * attempt)
    return None

def parse_m3u(text):
    """解析 m3u，返回 [(name, url), ...]"""
    channels = []
    lines = text.strip().splitlines()
    for i, line in enumerate(lines):
        line = line.strip()
        if line.startswith("#EXTINF"):
            name = line.split(",", 1)[1].strip() if "," in line else "unknown"
            for j in range(i + 1, min(i + 5, len(lines))):
                nxt = lines[j].strip()
                if nxt and not nxt.startswith("#"):
                    channels.append((name, nxt))
                    break
    return channels

def quick_check(url, timeout=6):
    """HEAD 测存活，返回 (ok, elapsed_ms)"""
    try:
        t0 = time.time()
        r = requests.head(url, headers=get_headers(), timeout=timeout, allow_redirects=True)
        return r.status_code < 400, (time.time() - t0) * 1000
    except:
        return False, 9999

def ffprobe_resolution(url, timeout=8):
    """ffprobe 抽一帧拿分辨率，返回 '1920x1080' 或 ''"""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", url],
            capture_output=True, text=True, timeout=timeout
        )
        if out.returncode == 0 and out.stdout.strip():
            w, h = out.stdout.strip().split(",")
            if w.isdigit() and h.isdigit() and int(w) > 0:
                return f"{w}x{h}"
    except:
        pass
    return ""

# ===================== 主流程 =====================

def main():
    log("🚀 开始抓取公网源")
    repo_root  = Path(__file__).resolve().parent.parent
    output_dir = repo_root / "output"
    output_dir.mkdir(exist_ok=True)
    json_path  = repo_root / "my_tvbox.json"

    # 加载旧配置（用于兜底）
    if json_path.exists():
        try:
            old_data = json.loads(json_path.read_text(encoding="utf-8"))
        except:
            old_data = {}
    else:
        old_data = {}

    all_live = []  # [(name, url, tag, ms)]

    for src in PUBLIC_SOURCES:
        name, url = src["name"], src["url"]
        log(f"📡 抓取: {name}")
        text = fetch_text(url, src["timeout"])
        if not text:
            warn(f"  ✖ 失败: {name}")
            continue

        # 保存原始备份
        (output_dir / f"{name}.m3u").write_text(text, encoding="utf-8")

        channels = parse_m3u(text)
        log(f"   解析 {len(channels)} 个频道，并发测速中...")

        ok = 0
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
            futs = {ex.submit(quick_check, u, 5): (n, u) for n, u in channels}
            for fut in as_completed(futs, timeout=120):
                n, u = futs[fut]
                is_ok, ms = fut.result()
                if is_ok:
                    ok += 1
                    all_live.append((n, u, name, int(ms)))

        log(f"   ✔ 存活 {ok}/{len(channels)}")

    # 去重：同 URL 保留最快
    log("🔧 去重 + 按延迟排序")
    seen, deduped = set(), []
    for item in sorted(all_live, key=lambda x: x[3]):
        if item[1] in seen:
            continue
        seen.add(item[1])
        deduped.append(item)

    top = deduped[:TOP_N_LIVE]
    log(f"🏆 保留 TOP {len(top)} 条")

    # ffprobe 深度探测分辨率
    log(f"🔬 ffprobe 探测分辨率（最多 {PROBE_LIMIT} 条）")
    for i, (n, u, tag, ms) in enumerate(top):
        if i >= PROBE_LIMIT:
            break
        res = ffprobe_resolution(u, 8)
        if res:
            top[i] = (n, u, tag, ms, res)
            log(f"   {n}: {res}")
        else:
            top[i] = (n, u, tag, ms, "")
            log(f"   {n}: 无视频流/超时")

    # ========== 构建 / 更新 my_tvbox.json ==========
    data = old_data if old_data else {
        "spider": "", "wallpaper": "", "sites": [], "lives": [],
        "rules": [], "hosts": [], "parses": []
    }

    # 静态影视源合并（首次或新增时写入）
    existing_keys = {s.get("key") for s in data.get("sites", [])}
    added = 0
    for site in STATIC_SITES:
        if site["key"] not in existing_keys:
            data.setdefault("sites", []).append(site)
            existing_keys.add(site["key"])
            added += 1
    if added:
        log(f"➕ 新增静态影视源 {added} 条")

    # 动态直播源：有抓取结果就覆盖，否则用旧的兜底
    if top:
        new_lives = []
        for n, u, tag, ms, res in top:
            item = {"name": f"{n} ({tag})", "type": 0, "url": u, "playerType": 2}
            if res:
                item["resolution"] = res
            item["_latency_ms"] = ms
            new_lives.append(item)
        data["lives"] = new_lives
        log(f"💾 lives 更新为 {len(new_lives)} 条")
    else:
        old_count = len(data.get("lives", []))
        log(f"⚠️ 本次抓取全部失败，保留旧 lives（{old_count} 条）兜底")

    # 写入 JSON
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 写 merged.m3u 备份
    lines = ["#EXTM3U"]
    for n, u, tag, ms, res in top:
        extra = f' resolution="{res}"' if res else ""
        lines.append(f'#EXTINF:-1 tvg-name="{n}" group-title="{tag}"{extra},{n}')
        lines.append(u)
    (output_dir / "merged.m3u").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 写一份状态报告
    report = {
        "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "sources_tried": len(PUBLIC_SOURCES),
        "sources_ok": len(set(t[2] for t in all_live)),
        "total_alive": len(all_live),
        "after_dedup": len(deduped),
        "final_lives": len(top),
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"📊 报告: {report}")
    log("✅ 全部完成")

if __name__ == "__main__":
    main()
