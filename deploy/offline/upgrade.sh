#!/usr/bin/env bash
# upgrade.sh — 服务器端增量升级（配合 scripts/offline-export.sh --delta 产出的 delta 包）
# 用法: ./upgrade.sh [delta_dir]      # delta_dir 默认 delta
#
# 流程：
#   1. 快照"将被替换"的镜像（回滚用） → docker load delta 新镜像
#   2. config_hash 变化 → 重新生成配置（generate-config.sh）
#   3. docker compose up -d（compose 引用 :latest，已被 load 覆盖为新版；重建变化服务）
#   4. pg_dump 备份 → 等待 gateway 健康 → 跑数据库迁移
#   5. 健康检查 → 失败则 reload 快照回滚；成功则更新服务器 manifest
#
# 回滚模型：镜像始终 :latest（load 即覆盖），故升级前对被替换镜像做 docker save 快照；
# 失败时 reload 快照恢复旧 :latest。成功后快照留在 upgrade-backup-<ver>/，确认稳定可删。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$SCRIPT_DIR"
P=eai-prod
COMPOSE=(-f docker/docker-compose.yaml -f docker/docker-compose.extensions.yaml -f docker/docker-compose.ragflow.yaml)
DELTA_DIR="${1:-delta}"

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; N='\033[0m'
log(){ echo -e "${G}[UP]${N} $*"; }
warn(){ echo -e "${Y}[UP]${N} $*"; }
err(){ echo -e "${R}[UP-ERR]${N} $*" >&2; }

# 镜像名 -> 安全文件名（与 offline-export.sh 的 image_to_filename 一致）
fname(){ echo "$1" | sed 's|[/:]|_|g; s|\.||g' | tr '[:upper:]' '[:lower:]'; }

# 探测可用 python3（读 manifest 用；Linux 服务器一般 python3，Windows 开发机可能需 python）
PY=""
for c in python3 python; do
  command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys;assert sys.version_info>=(3,)' 2>/dev/null && { PY="$c"; break; }
done
[ -n "$PY" ] || { err "需要 python3（读取 manifest.json）"; exit 1; }

NEW_MANIFEST="${DELTA_DIR}/manifest.json"
[ -f "$NEW_MANIFEST" ] || { err "缺少 ${NEW_MANIFEST}（先解压 delta 包到 ${DELTA_DIR}/）"; exit 1; }
NEW_TAG=$("$PY" - "$NEW_MANIFEST" <<'PY'
import json, sys; print(json.load(open(sys.argv[1])).get("version", ""))
PY
)
[ -n "$NEW_TAG" ] || { err "delta manifest 无 version 字段"; exit 1; }
NEW_CFG=$("$PY" - "$NEW_MANIFEST" <<'PY'
import json, sys; print(json.load(open(sys.argv[1])).get("config_hash", ""))
PY
)
ACCESS_PORT=$(grep '^PORT=' .env 2>/dev/null | cut -d= -f2 || echo 4026)

log "增量升级到 ${NEW_TAG}"

# 1. 快照被替换镜像 + load 新镜像
BACKUP_DIR="upgrade-backup-${NEW_TAG}"
if [ -d "${DELTA_DIR}/images" ]; then
  mkdir -p "$BACKUP_DIR"
  mapfile -t IMG_KEYS < <("$PY" - "$NEW_MANIFEST" <<'PY'
import json, sys
for k in json.load(open(sys.argv[1])).get("images", {}):
    print(k)
PY
)
  for img in "${IMG_KEYS[@]}"; do
    f=$(fname "$img")
    if [ -f "${DELTA_DIR}/images/${f}.tar" ]; then
      log "快照旧镜像: ${img} → ${BACKUP_DIR}/${f}.tar"
      docker save "$img" -o "${BACKUP_DIR}/${f}.tar" 2>/dev/null || warn "快照失败 ${img}（该镜像回滚将不可用）"
      log "load 新镜像: ${img}"
      docker load -i "${DELTA_DIR}/images/${f}.tar"
    fi
  done
else
  warn "无 ${DELTA_DIR}/images/（疑似纯配置变更，跳过镜像 load）"
fi

# 2. config_hash 变化才重新生成配置
CUR_CFG=$("$PY" - manifest.json <<'PY' 2>/dev/null
import json, sys; print(json.load(open(sys.argv[1])).get("config_hash", ""))
PY
)
if [ -n "$NEW_CFG" ] && [ "$NEW_CFG" != "$CUR_CFG" ]; then
  log "deploy.conf 变化（config_hash 不同），重新生成配置"
  bash scripts/generate-config.sh --conf deploy.conf --out . \
    --root "$SCRIPT_DIR" \
    --secret "$(grep '^BETTER_AUTH_SECRET=' .env | cut -d= -f2)" \
    --origin "http://$(hostname -I | awk '{print $1}'):${ACCESS_PORT}"
fi

# 3. 数据库备份（EAI-CUSTOM bug-3017: 必须在 up 之前——新 gateway 起来即跑 alembic
#    bootstrap，边迁移边 dump 会拿到撕裂快照；失败/空输出直接中止升级，没有回滚点不能继续）
log "备份数据库 → backup-pre-${NEW_TAG}.sql"
dump_db() { # $1=库名 $2=输出文件
  docker exec prod-eai-flow-postgres-ext pg_dump --clean --if-exists -U agentflow "$1" > "$2" \
    || { warn "pg_dump $1 失败（中止升级）"; exit 1; }
  [ -s "$2" ] || { warn "pg_dump $1 输出为空（中止升级）"; exit 1; }
}
dump_db agentflow "backup-pre-${NEW_TAG}.sql"
# EAI-CUSTOM (2026-08-29): 核心库已切 postgres（config.yaml database.backend: postgres，
# deerflow 库），线程/checkpoint 在这里，一并备份。--clean --if-exists 使 restore 可直接
# 灌回已建表的库（先 DROP 后 CREATE），配 ON_ERROR_STOP 使用。
dump_db deerflow "backup-pre-${NEW_TAG}-core.sql"

# 4. 应用变更 + 迁移
log "docker compose up -d"
docker compose -p "$P" "${COMPOSE[@]}" up -d
log "等待 gateway 健康..."
HEALTHY=0
for i in $(seq 1 40); do
  curl -sf "http://localhost:${ACCESS_PORT}/api/license/status" >/dev/null 2>&1 && { HEALTHY=1; break; }
  sleep 3
done
if [ "$HEALTHY" = 1 ]; then
  log "执行数据库迁移"
  docker exec prod-eai-flow-gateway python -m app.extensions.workflow.migration 2>&1 | tee -a logs/migration.log || warn "迁移失败/不需要"
fi

# 5. 健康检查 + 失败回滚
if ! curl -sf "http://localhost:${ACCESS_PORT}/api/license/status" >/dev/null 2>&1; then
  err "健康检查失败，回滚（reload 快照镜像）"
  if [ -d "$BACKUP_DIR" ]; then
    for t in "$BACKUP_DIR"/*.tar; do [ -f "$t" ] && docker load -i "$t"; done
    docker compose -p "$P" "${COMPOSE[@]}" up -d
    err "已回滚。排查：docker compose -p $P logs gateway"
  else
    err "无快照可回滚。手动排查：docker compose -p $P logs gateway"
  fi
  exit 1
fi

# 6. 成功：更新服务器 manifest
cp "$NEW_MANIFEST" manifest.json
log "升级完成: ${NEW_TAG}"
log "  回滚快照在 ${BACKUP_DIR}/；确认稳定后可删"
log "  手动回滚: for t in ${BACKUP_DIR}/*.tar; do docker load -i \"\$t\"; done && docker compose -p $P ${COMPOSE[*]} up -d"
