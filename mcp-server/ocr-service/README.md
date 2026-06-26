# eai-flow-ocr

合同扫描件表格 OCR 提取服务 — `contract-price-analysis` v2 的 Phase 0。

独立 docker 容器(**不进 gateway**):OCR / onnxruntime + poppler 是重依赖,隔离可避免拖垮核心 API 响应、避免 gateway 镜像膨胀。参照 `mcp-server/text-to-cad-mcp`、`cad-mcp` 模式,由 gateway 扩展与 contract-price-analysis 技能通过 HTTP 调用。

## 流水线

```
PDF --pdf2image--> 页 PNG (== 溯源预渲染图)
    --cv2 表格线检测--> 表格区域 bbox (带边线表格命中率高)
    --RapidOCR--> 单元格 text + bbox + confidence
    --坐标聚类--> 行 x 列重建
```

**Phase 0 为何用 cv2 线检测而非深度版面模型**:合同表格基本都带边线(已确认),线检测依赖轻、API 稳、命中率高。若命中率验证发现有无边线表格,在 `OcrEngine` 同接口下换 `rapid-table` 即可,调用方无感。

## 接口

### `POST /ocr` (multipart, `file=*.pdf`)

```json
{
  "pages": [{
    "page_no": 1, "page_width": 1700, "page_height": 2200,
    "tables": [{
      "bbox": [0.08, 0.2, 0.92, 0.8],
      "rows": [[{"text": "高压开关柜", "bbox": [0.1,0.21,0.3,0.25], "confidence": 0.97}, ...]],
      "row_count": 5, "col_count": 6, "mean_confidence": 0.93
    }],
    "preview_png_b64": "<base64>"
  }],
  "elapsed_ms": 4200,
  "engine": "pdf2image+cv2-lines+rapidocr-onnxruntime",
  "table_count": 1
}
```

所有 bbox 归一化到 0~1(相对**整页**),溯源比对时直接叠加在页 PNG 上,无需换算裁剪偏移。

### `GET /health`

`{"status":"ok","service":"eai-flow-ocr"}` — 不加载模型。

## 构建运行

```bash
# 容器(与项目一致,受限网络用清华源)
docker compose -p eai-docker -f docker/docker-compose-dev.yaml up -d --build ocr

curl http://localhost:8010/health
curl -F "file=@合同.pdf" http://localhost:8010/ocr | jq .
```

构建慢/卡 → 设 `UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`(见 cerebrum bug-cad-002)。

## Phase 0 命中率验证(本地,无需容器)

```bash
cd mcp-server/ocr-service
pip install -r requirements.txt          # 需系统 poppler (apt install poppler-utils / brew install poppler)
PYTHONPATH=. python verify_accuracy.py /path/合同.pdf --out ./verify-out
```

输出:每张表的行列重建(`page*_table*.txt`)+ 页 PNG(`page*.png`)+ 汇总(`summary.json`)。

**人工核验三指标**(决定能否进 Phase 1):
1. 表格命中率 — 应有的表是否都识别到
2. 行列结构 — 有无错位/漏行
3. **价格数字 OCR 准确率**(关键)— 对照原文逐数字核验

## 端口

`8010`(容器内 `OCR_PORT`,可改环境变量)。gateway 内部通过 `http://eai-flow-ocr:8010` 访问。

## 文件

| 文件 | 职责 |
|------|------|
| `server.py` | FastAPI: `/health` + `/ocr` |
| `ocr_engine.py` | OCR 引擎(pdf2image + cv2 线检测 + RapidOCR + 行列聚类) |
| `schemas.py` | Pydantic 响应模型(bbox 全归一化) |
| `verify_accuracy.py` | Phase 0 命中率验证脚本 |
| `Dockerfile` | 独立镜像(poppler + opencv + rapidocr) |
