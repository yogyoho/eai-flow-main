"""reparse 端点把 re_ocr 透传到子进程参数(缓存路径 vs 强制重OCR)。"""

import inspect


def test_service_builds_reocr_flag():
    from app.extensions.contract_price import service

    src = inspect.getsource(service.run_pipeline_subprocess)
    assert "re_ocr" in src and '"--re-ocr"' in src


def test_router_passes_reocr_to_service():
    from app.extensions.contract_price import routers

    src = inspect.getsource(routers.reparse_document)
    assert "re_ocr: bool = False" in src
    assert "re_ocr" in src.split("background.add_task")[1]
