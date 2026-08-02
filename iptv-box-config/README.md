# 📺 iptv-box-config

TVBox / 影视仓 合并多仓 JSON 配置，**每天自动抓取公网直播源 + 测速去重 + 合并输出**。

## 🤖 自动抓取流程

每次 GitHub Actions 触发时，会执行 `scripts/fetch_merge.py`：

```
抓取公网 m3u 源
   ├─ fanmingming (IPv6)
   ├─ zbds (IPv4)
   ├─ best-fan (央视 + 全部)
   ├─ Kimentanm
   ├─ cs3306 (IPTV-Sources)
   └─ Guovin (ipv4/result)
         ↓
   解析频道列表 + HEAD 测存活
         ↓
   并发去重，按延迟排序
         ↓
   ffprobe 探测分辨率（TOP 15）
         ↓
   覆盖写入 my_tvbox.json 的 lives 字段
   静态影视源（sites）保持不变
         ↓
   commit & push 回仓库
```

## 📁 文件结构

```
iptv-box-config/
├── .github/workflows/sync.yml   # 自动抓取+合并的 Actions 工作流
├── scripts/fetch_merge.py       # 抓取、测速、合并的核心脚本
├── my_tvbox.json               # 主配置（自动更新 lives，手动维护 sites）
├── output/                      # 每次抓取的原始 m3u 备份 + merged.m3u
├── sync_to_github.sh           # 手动推送脚本（一次性上传用）
└── README.md
```

## 🚀 快速使用

### 第 1 步：Fork / 建仓库
1. 把本仓库 Fork 到你的 GitHub 账号，或新建 `iptv-box-config` 仓库并上传这些文件
2. 进入 Settings → Actions → General → **Workflow permissions** 设为 **Read and write permissions**

### 第 2 步：开启 Actions
- 进入仓库 Actions 标签页 → 点 "I understand my workflows, go ahead and enable them"
- 工作流 `自动抓取公网源并合并` 会出现，可手动点 Run workflow 立即跑一次

### 第 3 步：把直链填到播放器

每天 04:00 / 16:00（北京时间）会自动更新，盒子只需填一次地址：

```
官方 raw  : https://raw.githubusercontent.com/你的用户名/iptv-box-config/main/my_tvbox.json
gh-proxy : https://gh-proxy.com/https://raw.githubusercontent.com/你的用户名/iptv-box-config/main/my_tvbox.json
iqiq 镜像: https://raw.iqiq.io/你的用户名/iptv-box-config/main/my_tvbox.json
```

> 国内盒子优先用 gh-proxy / iqiq 镜像。

## ✏️ 自定义

### 加/删影视源（永久保留）
直接编辑 `my_tvbox.json` 的 `sites` 数组，Actions 不会覆盖它们。

### 加/删直播源抓取目标
编辑 `scripts/fetch_merge.py` 顶部的 `PUBLIC_SOURCES` 列表，加一条：
```python
{"name": "my_source", "url": "https://example.com/list.m3u", "type": "m3u", "timeout": 15}
```

### 调整保留数量
`TOP_N_LIVE = 30` 控制最终保留多少条最快直播源。

### 改抓取频率
编辑 `.github/workflows/sync.yml` 里的 cron 表达式。

## ⚠️ 注意

- **Actions 免费额度**：公开仓库每月 2000 分钟，本工作流每次约 5-10 分钟，一天两次完全够用
- **ffprobe 探测**只测 TOP 15 条，避免超时
- 公开源版权灰色，**仅限家庭自用**
- 如某抓取源长期 404，编辑 `fetch_merge.py` 把它注释掉即可

## 🔧 手动触发

不想等定时？进 GitHub → Actions → 选工作流 → **Run workflow** 按钮，立刻跑一次。
