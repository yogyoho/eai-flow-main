"""python-docx 50MB E2E: full pipeline, doc_parser_max_mb=100."""
import asyncio, time, sys, os
sys.path.insert(0, "/app/backend")
sys.path.insert(0, "/app/backend/packages/harness")

from app.extensions.knowledge_factory.pipeline import ExtractionPipeline
from app.extensions.knowledge_factory.schemas import ExtractionConfig

filepath = "/app/backend/.deer-flow/test_lingtai_50mb.docx"
fsize_mb = os.path.getsize(filepath) / 1024 / 1024

config = ExtractionConfig(llm_model="", max_depth=4, doc_parser_max_mb=100)

report_docs = [{
    "id": "test-003", "name": "灵台矿区环评报告书.docx",
    "kb_id": "test-kb", "ragflow_document_id": None,
    "ragflow_dataset_id": None, "file_path": filepath, "file_type": "docx",
}]

pipeline = ExtractionPipeline(llm_model=None)

async def main():
    t0 = time.time()
    print(f"=== doc_parser_max_mb=100 | {fsize_mb:.1f}MB ===", flush=True)
    print(f"开始: {time.strftime('%H:%M:%S')}", flush=True)
    try:
        result = await pipeline.run(
            task_id="perf-test-003", report_documents=report_docs,
            config=config, domain="environmental_impact_assessment",
        )
        elapsed = time.time() - t0
        print(f"✅ 完成 {elapsed:.0f}s ({elapsed/60:.1f}min)", flush=True)
        print(f"{result.chapters}章/{result.total_sections}节 完整度:{result.completeness_score}%", flush=True)
        for s in result.step_summaries:
            print(f"  [{s['status']}] {s['name']}: {s['detail']} ({s['duration']})", flush=True)
    except Exception as e:
        elapsed = time.time() - t0
        print(f"❌ {type(e).__name__}: {e} ({elapsed:.0f}s)", flush=True)

asyncio.run(main())
