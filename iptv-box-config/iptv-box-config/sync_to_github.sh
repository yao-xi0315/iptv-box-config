#!/bin/bash
# ============================================================
#  sync_to_github.sh
#  把 my_tvbox.json 推送到 GitHub 仓库，并打印 raw 直链
#  使用前：先填下面的 3 个变量（或导出为环境变量）
# ============================================================

set -e

# ====== 你需要修改的 3 个变量 ======
GITHUB_USER="${GITHUB_USER:-你的用户名}"          # 改成你的 GitHub 用户名
REPO_NAME="${REPO_NAME:-iptv-box-config}"         # 仓库名（默认即可）
GITHUB_TOKEN="${GITHUB_TOKEN:-}"                  # 改成你的 Personal Access Token
# ==================================

BRANCH="${BRANCH:-main}"
FILE_NAME="my_tvbox.json"
COMMIT_MSG="update tvbox config $(date '+%Y-%m-%d %H:%M:%S')"

# 颜色
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

echo -e "${YELLOW}▶ 检查配置...${NC}"

if [ "$GITHUB_USER" = "你的用户名" ] || [ -z "$GITHUB_TOKEN" ]; then
  echo -e "${RED}✖ 请先编辑脚本，填入 GITHUB_USER 和 GITHUB_TOKEN${NC}"
  echo "  也可以临时用环境变量："
  echo "  GITHUB_USER=xxx GITHUB_TOKEN=ghp_xxx ./sync_to_github.sh"
  exit 1
fi

# 进入脚本所在目录
cd "$(dirname "$0")"

if [ ! -f "$FILE_NAME" ]; then
  echo -e "${RED}✖ 找不到 $FILE_NAME${NC}"
  exit 1
fi

# 验证 JSON 合法
python3 -c "import json;json.load(open('$FILE_NAME'))" && echo -e "${GREEN}✔ JSON 格式正确${NC}"

# 初始化 git（如果还没初始化）
if [ ! -d .git ]; then
  echo -e "${YELLOW}▶ 初始化 git 仓库${NC}"
  git init -b "$BRANCH"
  git remote add origin "https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${REPO_NAME}.git"
fi

echo -e "${YELLOW}▶ 提交并推送...${NC}"
git add "$FILE_NAME"
git commit -m "$COMMIT_MSG" || echo "（无新变更，跳过提交）"
git push -u origin "$BRANCH"

# 输出直链
RAW_URL="https://raw.githubusercontent.com/${GITHUB_USER}/${REPO_NAME}/${BRANCH}/${FILE_NAME}"
# 国内加速镜像（可选）
PROXY_URL="https://gh-proxy.com/${RAW_URL}"
IPAQ_URL="https://raw.iqiq.io/${GITHUB_USER}/${REPO_NAME}/${BRANCH}/${FILE_NAME}"

echo ""
echo -e "${GREEN}✅ 推送成功！${NC}"
echo ""
echo "━━━ 直链地址（三选一） ━━━"
echo -e "  官方 raw  : ${GREEN}${RAW_URL}${NC}"
echo -e "  gh-proxy : ${YELLOW}${PROXY_URL}${NC}"
echo -e "  iqiq 镜像: ${YELLOW}${IPAQ_URL}${NC}"
echo ""
echo "👉 把上面任一地址粘到 TVBox / 影视仓 的「配置地址」即可"
