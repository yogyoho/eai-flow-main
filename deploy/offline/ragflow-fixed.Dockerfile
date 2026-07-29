# EAI-CUSTOM: RAGFlow v0.25.3 离线修复镜像
#   - F.11: entrypoint 调用 pip，但 venv 未加入 PATH（只有 pip3 没有 pip）
#   - F.13: 首次初始化需从 Azure 下载 cl100k_base.tiktoken，内网无公网会失败
# 构建在有网开发机执行（base 镜像需先 make docker-start 拉取），把修复烘焙进镜像。
FROM infiniflow/ragflow:v0.25.3

# F.11: 把 venv 加入 PATH 并补 pip 软链（entrypoint 的 `pip` 调用才能解析）
ENV PATH=/ragflow/.venv/bin:${PATH}
RUN ln -sf pip3 /ragflow/.venv/bin/pip || true

# F.13: 构建期（开发机有网）预下载 tiktoken 的 cl100k_base 编码文件并烘焙进镜像，
# 离线服务器首次初始化即无需连 openaipublic.blob.core.windows.net。
# best-effort：下载失败不阻断构建（开发机无网时跳过，服务器侧仍可走 RAGFLOW_HTTP_PROXY 兜底）。
RUN /ragflow/.venv/bin/python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')" 2>/dev/null || true
