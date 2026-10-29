#!/usr/bin/env bash
# 把 OB/ 打包成压缩包放到指定目录。用法：./memory-backup.sh <备份放哪> [家目录路径]
# 备份放哪：先问她，别自己挑（比如她的私有云盘同步文件夹）。
set -euo pipefail

DEST="${1:?用法: memory-backup.sh <备份放哪> [家目录路径]}"
HOME_DIR="${2:-$HOME/home-of-machine}"

mkdir -p "$DEST"
STAMP="$(date '+%Y%m%d-%H%M')"
tar -czf "$DEST/OB-$STAMP.tar.gz" -C "$HOME_DIR" OB
echo "已备份：$DEST/OB-$STAMP.tar.gz"

# 只留最近 8 份，旧的删掉（删之前这里只列出，不真删，除非她同意）
ls -1t "$DEST"/OB-*.tar.gz | tail -n +9 || true
