# 📺 iptv-box-config

TVBox / 影视仓 合并多仓 JSON 配置，一键同步到 GitHub 并生成直链。

## 📁 文件说明

| 文件 | 作用 |
|---|---|
| `my_tvbox.json` | 主配置文件（6 条影视源 + 4 条直播源） |
| `sync_to_github.sh` | 自动同步脚本（推送到 GitHub + 打印直链） |
| `README.md` | 本文件 |

## 🚀 快速使用（3 步）

### 第 1 步：创建 GitHub 仓库
1. 登录 https://github.com → New repository
2. 仓库名填 `iptv-box-config`，**Public**，**不要**勾选初始化 README
3. 点 Create

### 第 2 步：生成 Personal Access Token
1. 打开 https://github.com/settings/tokens?type=beta （Fine-grained tokens）
2. Token name 随便填，Repository access 选刚才建的 `iptv-box-config`
3. Permissions → Contents 选 **Read and write**
4. 生成后**复制保存**（只显示一次）

### 第 3 步：跑同步脚本

**方式 A：命令行传参（推荐，不用改文件）**
```bash
cd iptv-box-config
GITHUB_USER=你的用户名 \
GITHUB_TOKEN=ghp_你的token \
./sync_to_github.sh
```

**方式 B：编辑脚本后运行**
用记事本打开 `sync_to_github.sh`，把第 9-11 行改成你的用户名和 token，然后：
```bash
chmod +x sync_to_github.sh
./sync_to_github.sh
```

成功后终端会打印三条直链，**任选一条**粘到 TVBox / 影视仓 的「配置地址」即可。

## 🔗 直链格式

```
官方 raw  : https://raw.githubusercontent.com/用户名/iptv-box-config/main/my_tvbox.json
gh-proxy : https://gh-proxy.com/https://raw.githubusercontent.com/用户名/iptv-box-config/main/my_tvbox.json
iqiq 镜像: https://raw.iqiq.io/用户名/iptv-box-config/main/my_tvbox.json
```

> 国内盒子推荐用 **gh-proxy** 或 **iqiq** 镜像，raw 原链偶尔抽风。

## ✏️ 自定义源

编辑 `my_tvbox.json`：
- **加影视源**：在 `sites` 数组里加一条 `{"key":"xx","name":"显示名","type":3,"api":"https://xxx.json"}`
- **加直播源**：在 `lives` 数组里加一条 `{"name":"xx","type":0,"url":"https://xxx.m3u"}`
- 改完跑一次 `./sync_to_github.sh` 就自动更新

## ⚠️ 安全提醒

- **Token 不要泄露**，不要提交到公开仓库。建议用 Fine-grained token 且只授权本仓库。
- 仓库设成 **Private** 也行，但 raw 直链需要 token 才能访问，盒子端不方便。建议保持 Public 但**单独建一个小号/专用仓库**，别跟你的主账号重要代码混一起。
- 公开源版权灰色，**仅限家庭自用**，不要公开转发。

## 🛠 定时自动更新（可选）

如果想每天自动同步一次（比如源挂了自动切），可以用 GitHub Actions 或 crontab 定时跑脚本。需要的话我再帮你加 workflow 文件。
