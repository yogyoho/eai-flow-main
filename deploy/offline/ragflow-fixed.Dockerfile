# EAI-CUSTOM: RAGFlow 离线修复镜像（2026-09-04 随 dev 升级到 v0.27.1，bug-3101）
#   - F.11: entrypoint 调用 pip，但 venv 未加入 PATH（只有 pip3 没有 pip）
#     （已在 v0.27.1 运行镜像上实测：/ragflow/.venv/bin 只有 pip3，pip 不在 PATH，前提仍成立）
#   - F.13: 首次初始化需从 Azure 下载 cl100k_base.tiktoken，内网无公网会失败
# 构建在有网开发机执行（base 镜像需先 make docker-start 拉取），把修复烘焙进镜像。
# 注意：若未来 base 镜像调整了 /ragflow/.venv 布局，下面 tiktoken 预下载一步会
# 在构建期硬失败（这是有意的——宁可导出失败，不可 ship 假离线镜像）。
FROM infiniflow/ragflow:v0.27.1

# F.11: 把 venv 加入 PATH 并补 pip 软链（entrypoint 的 `pip` 调用才能解析）
ENV PATH=/ragflow/.venv/bin:${PATH}
# F.13: tiktoken 缓存目录钉在 /root/.cache（在 /ragflow 之外，不被 named volume prod-ragflow-data 覆盖）
ENV TIKTOKEN_CACHE_DIR=/root/.cache/tiktoken
RUN ln -sf pip3 /ragflow/.venv/bin/pip || true

# F.13: 构建期（开发机有网）预下载 cl100k_base.tiktoken 并烘焙进镜像。
# 离线服务器首次初始化即无需连 openaipublic.blob.core.windows.net。
# 关键：**校验**文件落地（旧版 `|| true` 吞掉下载失败 → 镜像没文件 → 离线仍下载 → crash）。
# 下载失败直接让构建失败（别 ship 一个假离线镜像）。
RUN mkdir -p /root/.cache/tiktoken && \
    /ragflow/.venv/bin/python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')" && \
    test -n "$(ls -A /root/.cache/tiktoken)" || (echo "FATAL: tiktoken cl100k_base 预下载失败" && exit 1)
