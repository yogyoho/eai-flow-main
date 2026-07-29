# 每客户品牌资源目录

把**该客户**的静态品牌资源放到这里（或 `deploy.conf` 里 `BRAND_ASSETS_DIR` 指向的目录）：

- `favicon.ico` — 浏览器 tab 图标
- `favicon.svg` — 矢量 favicon
- `logo.svg` — 页头 logo

## 工作方式

`scripts/offline-export.sh` 导出离线包时：
1. 读 `deploy.conf` 的 `BRAND_NAME` / `BRAND_FOOTER`，作为 `--build-arg` 注入前端 prod 构建（`NEXT_PUBLIC_BRAND_NAME`/`NEXT_PUBLIC_BRAND_FOOTER`，next build 内联烘焙）。
2. 把本目录的 `favicon.*` / `logo.svg` 拷进 `frontend/public/`，构建期 `COPY` 烘焙进镜像。
3. 构建后 `git checkout` 恢复 `frontend/public/`，不污染源码树。

文字品牌（显示名 `BRAND_NAME` 出现在页标题/登录/setup；页脚 `BRAND_FOOTER`）由 `frontend/src/brand.ts` 读取。
未提供某文件/值则用源码默认（favicon 默认、显示名默认 `EAIFlow`、页脚默认 MIT License 行）。

## 多客户

每客户一个目录（如 `brands/customer-a/`），导出前在 `deploy.conf` 里设 `BRAND_ASSETS_DIR=./brands/customer-a` + 该客户的 `BRAND_NAME`/`BRAND_FOOTER`，再跑 `offline-export.sh`。
