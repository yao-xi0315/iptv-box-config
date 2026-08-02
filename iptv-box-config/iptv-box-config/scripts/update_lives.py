#!/usr/bin/env python3
"""
update_lives.py
================
每天被 GitHub Actions 调用：
  1. 抓取多个公网 m3u 直播源
  2. HEAD 测存活 + 按延迟排序去重
  3. 读取仓库里的 my_tvbox.json
  4. 只更新 lives 字段，sites 字段保持不变
  5. 写回 my_tvbox.json
  6. 额外输出 output/merged.m3u 备份

设计原则：
  - 单条源失败不影响其他
  - 全部失败时用旧 lives 兜底
  - 不修改 sites（影视源由用户手动维护）
"""

import json
import time
import random
import subprocess
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# ===================== 日志 =====================
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
log = logging.info
warn = logging.warning

# ===================== 配置 =====================

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "VLC/3.0.20 LibVLC/3.0.20",
    "IPTV-Client/1.0",
]

def get_headers():
    return {
        "User-Agent": random.choice(UA_POOL),
        "Accept": "*/*",
        "Connection": "close",
    }

# 要抓取的公网直播源
PUBLIC_SOURCES = [
    {"name": "fanmingming_ipv6", "url": "https://live.fanmingming.cn/tv/m3u/ipv6.m3u", "timeout": 20},
    {"name": "fanmingming_ipv4", "url": "https://live.fanmingming.cn/tv/m3u/iptv4.m3u", "timeout": 20},
    {"name": "zbds_ipv4",         "url": "https://live.zbds.top/tv/iptv4.m3u", "timeout": 20},
    {"name": "bestfan_cctv",      "url": "https://gh-proxy.com/https://raw.githubusercontent.com/best-fan/iptv-sources/master/cn_cctv.m3u8", "timeout": 25},
    {"name": "bestfan_all",       "url": "https://gh-proxy.com/https://raw.githubusercontent.com/best-fan/iptv-sources/master/cn_all.m3u8", "timeout": 25},
    {"name": "kimentanm",        "url": "https://gh.927223.xyz/https://raw.githubusercontent.com/Kimentanm/aptv/master/m3u/iptv.m3u", "timeout": 25},
    {"name": "cs3306",            "url": "https://raw.githubusercontent.com/cs3306/IPTV-Sources/main/data/output/iptv_collection.m3u", "timeout": 25},
    {"name": "guovin_ipv4",      "url": "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv4/result.m3u", "timeout": 25},
]

TOP_N_LIVE  = 50   # 最终保留最快源数量
CONCURRENCY = 10
RETRY       = 2

# ===================== 工具函数 =====================

def fetch_text(url, timeout=20):
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
    try:
        t0 = time.time()
        r = requests.head(url, headers=get_headers(), timeout=timeout, allow_redirects=True)
        return r.status_code < 400, int((time.time() - t0) * 1000)
    except:
        return False, 9999

# ===================== 主流程 =====================

def main():
    log("🚀 开始抓取公网直播源")
    repo_root  = Path(__file__).resolve().parent.parent
    output_dir = repo_root / "output"
    output_dir.mkdir(exist_ok=True)
    json_path  = repo_root / "my_tvbox.json"

    # 加载旧配置
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            log(f"📂 加载现有 my_tvbox.json（sites={len(data.get('sites',[]))} lives={len(data.get('lives',[]))}）")
        except Exception as e:
            warn(f"JSON 解析失败 {e}，用空模板")
            data = {}
    else:
        data = {}

    # 确保字段存在
    for k in ["spider", "wallpaper", "sites", "lives", "rules", "hosts", "parses"]:
        data.setdefault(k, [] if k != "spider" and k != "wallpaper" else "")
    if data.get("spider") is None: data["spider"] = ""
    if data.get("wallpaper") is None: data["wallpaper"] = ""

    all_live = []

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
            for fut in as_completed(futs, timeout=180):
                n, u = futs[fut]
                is_ok, ms = fut.result()
                if is_ok:
                    ok += 1
                    all_live.append((n, u, name, ms))

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
    log(f"🏆 保留 TOP {len(top)} 条直播源")

    # 构建新的 lives
    if top:
        new_lives = []
        for n, u, tag, ms in top:
            item = {
                "name": f"{n} ({tag})",
                "type": 0,
                "url": u,
                "playerType": 2,
            }
            new_lives.append(item)
        data["lives"] = new_lives
        log(f"💾 lives 更新为 {len(new_lives)} 条")

        # 写 merged.m3u 备份
        lines = ["#EXTM3U"]
        for n, u, tag, ms in top:
            lines.append(f'#EXTINF:-1 tvg-name="{n}" group-title="{tag}",{n}')
            lines.append(u)
        (output_dir / "merged.m3u").write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        old_count = len(data.get("lives", []))
        log(f"⚠️ 本次抓取全部失败，保留旧 lives（{old_count} 条）兜底")

    # 写回 JSON
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"✅ 写入 {json_path}")

    # 写报告
    report = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
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

if __name__ == "__main__":
    main()
