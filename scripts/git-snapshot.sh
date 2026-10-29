#!/usr/bin/env bash
# 给家目录做一次 git 快照。用法：./git-snapshot.sh [家目录路径]
# 默认家目录是 ~/home-of-machine。第一次会自动 git init。
set -euo pipefail

HOME_DIR="${1:-$HOME/home-of-machine}"
cd "$HOME_DIR"

if [ ! -d .git ]; then
  git init -q
  printf '.env\n*.key\n*.token\n' >> .gitignore
fi

git add -A
if git diff --cached --quiet; then
  echo "没有变化，不提交"
  exit 0
fi
git -c user.name="home-snapshot" -c user.email="snapshot@local" \
  commit -q -m "snapshot $(date '+%Y-%m-%d %H:%M')"
echo "已提交：$(git log -1 --format='%h %s')"
