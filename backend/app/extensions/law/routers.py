"""FastAPI routers for law management."""

import logging
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.config import get_extensions_config
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

from .schemas import (
    FileParseResponse,
    IndustriesResponse,
    LawCreate,
    LawListResponse,
    LawResponse,
    LawStatistics,
    LawTemplateRelationCreate,
    LawTemplateRelationResponse,
    LawUpdate,
    RAGFlowInitResponse,
    RAGFlowStatusResponse,
)
from .service import _KB_SEED_CONFIG, LawService, merge_industries, seed_config_diff

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kf/laws", tags=["Laws"])


def _can_access_kf(current_user: CurrentUser) -> bool:
    """检查用户是否有知识工厂访问权限"""
    # 管理员或系统访问权限
    if current_user.role_name in ["超级管理员", "admin", "系统管理员"]:
        return True
    return "system:access" in getattr(current_user, "permissions", [])


CurrentUserWithAccess = Annotated[CurrentUser, Depends(require_permission("system:access"))]


# =============================================================================
# 静态路由 (必须在 /{law_id} 之前定义，避免被路径参数路由抢先匹配)
# =============================================================================


@router.get("", response_model=LawListResponse)
async def list_laws(
    law_type: str | None = Query(None, description="法规类型"),
    status: str | None = Query(None, description="状态筛选"),
    keyword: str | None = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserWithAccess = None,
):
    """获取法规列表"""
    laws, total = await LawService.list_laws(
        db,
        law_type=law_type,
        status=status,
        keyword=keyword,
        page=page,
        limit=limit,
    )

    # 获取统计信息
    by_type = await LawService.get_by_type_counts(db)
    by_status = await LawService.get_by_status_counts(db)

    return LawListResponse(
        laws=[LawService._law_to_response(law) for law in laws],
        total=total,
        by_type=by_type,
        by_status=by_status,
    )


@router.post("", response_model=LawResponse, status_code=status.HTTP_201_CREATED)
async def create_law(
    data: LawCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserWithAccess = None,
):
    """创建法规"""
    law = await LawService.create_law(db, data)
    synced, _ = await LawService.sync_to_ragflow(db, law, owner_id=current_user.id)
    if not synced:
        logger.warning("Law created but RAGFlow sync failed: %s", law.id)
    return LawService._law_to_response(law)


@router.get("/statistics", response_model=LawStatistics)
async def get_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserWithAccess = None,
):
    """获取法规统计信息"""
    return await LawService.get_statistics(db)


@router.get("/ragflow-status", response_model=RAGFlowStatusResponse)
async def get_ragflow_status(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserWithAccess = None,
):
    """获取所有法规类型的RAGFlow知识库状态"""
    return await LawService.get_ragflow_status(db, owner_id=current_user.id)


async def _converge_law_kb(
    rf_client,  # RAGFlowClient 实例(测试传 fake)
    kb_name: str,
    industry_tag_ids: list[str],
) -> tuple[str, dict, str | None]:
    """单库幂等收敛:返回 (状态 aligned|updated|created, diffs, dataset_id)。"""
    seed = _KB_SEED_CONFIG[kb_name]
    parser_config = dict(seed["parser_config"])
    if kb_name == "ragflow-laws-standards" and industry_tag_ids:
        parser_config["tag_kb_ids"] = industry_tag_ids
    elif kb_name == "ragflow-laws-standards":
        # 标签集缺失/查询失败时不携带空绑定,diff 跳过该键,避免 PUT 解绑现网绑定
        parser_config.pop("tag_kb_ids", None)

    existing = await rf_client.get_dataset_by_name(kb_name)
    if existing:
        dataset_id = existing.get("id")
        cur_data = (await rf_client.get_dataset(dataset_id)).get("data") or {}
        # 不变量:种子顶层键必须只有 chunk_method/parser_config——diff 与 PUT 的键集合才一致;
        # description 仅创建时设置,有意不参与收敛
        seed_for_diff = {k: seed[k] for k in ("chunk_method", "parser_config")}
        diff = seed_config_diff(cur_data, {**seed_for_diff, "parser_config": parser_config})
        if diff:
            await rf_client.update_dataset(
                dataset_id,
                chunk_method=seed["chunk_method"],
                parser_config=parser_config,
            )
            return "updated", {k: list(v) for k, v in diff.items()}, dataset_id
        return "aligned", {}, dataset_id

    result = await rf_client.create_dataset(
        name=kb_name,
        description=f"法规标准库 - {kb_name}",
        chunk_method=seed["chunk_method"],
        parser_config=parser_config,
    )
    return "created", {}, result.get("data", {}).get("id")


@router.post("/init-ragflow", response_model=RAGFlowInitResponse)
async def init_ragflow_knowledge_bases(
    law_type: str | None = Query(None, description="指定要初始化的类型，不指定则全部"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserWithAccess = None,
):
    """
    初始化RAGFlow知识库

    - 不指定type: 创建所有2个知识库（ragflow-laws-legal + ragflow-laws-standards）
    - 指定type: 只创建该类型所属的知识库
    """
    config = get_extensions_config()
    if not config.ragflow.api_key:
        raise HTTPException(status_code=503, detail="RAGFlow服务未配置，请先配置RAGFlow API Key")

    from app.extensions.knowledge.client import RAGFlowClient

    rf_client = RAGFlowClient()

    # 检查RAGFlow连接
    try:
        if not await rf_client.is_available():
            raise HTTPException(status_code=503, detail="RAGFlow服务不可用")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"RAGFlow连接失败: {str(e)}")

    from .service import RAGFLOW_DATASET_GROUPS, RAGFLOW_KB_MAPPING

    # 确定需要初始化的知识库名称（去重）
    if law_type:
        kb_name = RAGFLOW_KB_MAPPING.get(law_type)
        if not kb_name:
            raise HTTPException(status_code=400, detail=f"未知的法规类型: {law_type}")
        datasets_to_init = {kb_name: RAGFLOW_DATASET_GROUPS[kb_name]}
    else:
        datasets_to_init = dict(RAGFLOW_DATASET_GROUPS)

    results = {"created": [], "aligned": [], "updated": [], "diffs": {}, "already_exists": [], "failed": [], "registered": []}

    # 行业标签集:存在则绑定到 standards 种子(块级贴标 v0.27.1 实测未生效,绑定无害、上游修复即用)
    industry_tag_ids: list[str] = []
    try:
        tag_ds = await rf_client.get_dataset_by_name("行业标签集")
        if tag_ds:
            industry_tag_ids = [tag_ds["id"]]
    except Exception as e:
        logger.warning("解析行业标签集失败(忽略): %s", e)

    for kb_name in datasets_to_init:
        try:
            seed = _KB_SEED_CONFIG[kb_name]
            status, diffs, dataset_id = await _converge_law_kb(rf_client, kb_name, industry_tag_ids)
            if status == "created":
                results["created"].append(kb_name)
                logger.info(f"创建RAGFlow知识库成功: {kb_name} (chunk_method={seed['chunk_method']})")
            elif status == "updated":
                results["updated"].append(kb_name)
                results["diffs"][kb_name] = diffs
                logger.info("知识库配置已收敛到种子: %s diff=%s", kb_name, diffs)
            else:
                results["aligned"].append(kb_name)

            if dataset_id:
                # chunk_method 单一真相源为种子,不再取循环变量(消除双源漂移)
                registered = await LawService._ensure_kb_registered(db, current_user.id, kb_name, dataset_id, seed["chunk_method"])
                if registered:
                    results["registered"].append(kb_name)
        except Exception as e:
            results["failed"].append({"kb": kb_name, "error": str(e)})
            logger.error(f"初始化RAGFlow知识库失败: {kb_name} - {e}")

    return RAGFlowInitResponse(**results)


@router.get("/industries", response_model=IndustriesResponse)
async def list_industries(
    current_user: CurrentUserWithAccess = None,
):
    """行业领域候选 = 「行业标签集」标签块的 tag_kwd ∪ 兜底名单。标签集不存在返回兜底名单。"""
    from app.extensions.knowledge.client import RAGFlowClient

    rf_client = RAGFlowClient()
    found: list[str] = []
    try:
        tag_ds = await rf_client.get_dataset_by_name("行业标签集")
        if tag_ds:
            docs = (await rf_client.list_documents(tag_ds["id"])).get("data", {}).get("docs", [])
            for doc in docs:
                # 翻页读取全部标签块,消除 >100 块时的静默截断
                page = 1
                while True:
                    r = await rf_client.list_chunks(tag_ds["id"], doc["id"], page=page, size=100)
                    data = r.get("data") or {}
                    chunks = data.get("chunks") or []
                    for ch in chunks:
                        found.extend(ch.get("tag_kwd") or [])
                    total = data.get("total") or 0
                    if not chunks or page * 100 >= total:
                        break
                    page += 1
    except Exception as e:
        logger.warning("行业标签集读取失败(回退兜底名单): %s", e)
    return IndustriesResponse(industries=merge_industries(found))


@router.post("/sync-all")
async def sync_all_laws_to_ragflow(
    law_type: str | None = Query(None, description="指定类型，不指定则全部"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserWithAccess = None,
):
    """批量同步法规到RAGFlow"""
    laws, _ = await LawService.list_laws(db, law_type=law_type, limit=1000)

    synced = 0
    failed = 0
    skipped = 0

    for law in laws:
        if law.is_synced == "synced":
            skipped += 1
            continue

        success, _ = await LawService.sync_to_ragflow(db, law, owner_id=current_user.id)
        if success:
            synced += 1
        else:
            failed += 1

    return {
        "message": "同步完成",
        "synced": synced,
        "failed": failed,
        "skipped": skipped,
        "total": len(laws),
    }


@router.get("/templates/{template_id}/laws", response_model=LawListResponse)
async def get_template_laws(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserWithAccess = None,
):
    """获取引用某模板的所有法规"""
    laws = await LawService.get_template_laws(db, template_id)
    return LawListResponse(laws=laws, total=len(laws), by_type={}, by_status={})


# =============================================================================
# 文件解析 / 导入 (必须在 /{law_id} 之前)
# =============================================================================


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}


@router.post("/parse-file", response_model=FileParseResponse)
async def parse_law_file(
    file: UploadFile,
    current_user: CurrentUserWithAccess = None,
):
    """
    上传法规文件（PDF/Word/TXT/MD），自动解析并返回文本内容。
    """
    import os

    ext = os.path.splitext(file.filename or "")[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型，仅支持: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    import shutil
    import tempfile

    tmp_path = None
    try:
        suffix = ext if ext in {".pdf", ".docx", ".doc"} else ".txt"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name

        content = await LawService.parse_file_content(tmp_path, ext)

        return FileParseResponse(
            filename=file.filename or "unknown",
            content=content,
            char_count=len(content),
            success=True,
        )
    except Exception as e:
        logger.error(f"解析法规文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/import-with-file", response_model=LawResponse, status_code=status.HTTP_201_CREATED)
async def import_law_with_file(
    title: str = Form(..., description="法规标题"),
    law_number: str | None = Form(None, description="法规编号"),
    law_type: str = Form(..., description="法规类型"),
    department: str | None = Form(None, description="发布部门"),
    effective_date: str | None = Form(None, description="生效日期"),
    keywords: str | None = Form(None, description="关键词，逗号分隔"),
    referred_laws: str | None = Form(None, description="被引用法规，逗号分隔"),
    sector: str | None = Form(None, description="行业领域(如 地质勘查/环境评价),用作 RAGFlow 文档名前缀"),
    file: UploadFile | None = Form(None, description="法规文件 PDF/Word/TXT"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserWithAccess = None,
):
    """
    一站式导入法规：同时上传文件并填写元数据，文件自动解析为正文。

    - title, law_type 为必填
    - file 为可选，不传则创建仅有元数据的记录
    """
    from datetime import datetime

    content = None
    tmp_path = None
    original_file_name = file.filename if file else None

    if file and file.filename:
        ext = os.path.splitext(file.filename or "")[-1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型，仅支持: {', '.join(ALLOWED_EXTENSIONS)}",
            )

        import shutil as _shutil
        import tempfile as _tmp

        try:
            suffix = ext if ext in {".pdf", ".docx", ".doc"} else ".txt"
            with _tmp.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                _shutil.copyfileobj(file.file, tmp)
                tmp_path = tmp.name

            content = await LawService.parse_file_content(tmp_path, ext)
        except Exception as e:
            logger.error(f"解析法规文件失败: {e}")
            raise HTTPException(status_code=500, detail=f"文件解析失败: {str(e)}")

    effective_dt = None
    if effective_date:
        try:
            effective_dt = datetime.fromisoformat(effective_date)
        except ValueError:
            effective_dt = None

    kw_list = [k.strip() for k in keywords.split(",")] if keywords else None
    ref_list = [r.strip() for r in referred_laws.split(",")] if referred_laws else None

    data = LawCreate(
        title=title,
        law_number=law_number,
        law_type=law_type,
        status="active",
        department=department,
        effective_date=effective_dt,
        content=content,
        keywords=kw_list,
        referred_laws=ref_list,
        sector=sector,
    )

    try:
        law = await LawService.create_law(db, data)

        synced, sync_err = await LawService.sync_to_ragflow(
            db,
            law,
            file_path=tmp_path,
            file_name=original_file_name,
            owner_id=current_user.id,
        )
        if not synced:
            logger.warning("Law imported but RAGFlow sync failed: %s, reason: %s", law.id, sync_err)
            if hasattr(db, "refresh"):
                await db.refresh(law)

        return LawService._law_to_response(law)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# =============================================================================
# 动态路由 /{law_id} (必须在静态路由之后)
# =============================================================================


@router.get("/{law_id}", response_model=LawResponse)
async def get_law(
    law_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserWithAccess = None,
):
    """获取单个法规详情"""
    law = await LawService.get_law(db, law_id)
    if not law:
        raise HTTPException(status_code=404, detail="法规不存在")

    # 增加查看次数
    await LawService.increment_view_count(db, law)

    return LawService._law_to_response(law)


@router.put("/{law_id}", response_model=LawResponse)
async def update_law(
    law_id: str,
    data: LawUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserWithAccess = None,
):
    """更新法规"""
    law = await LawService.get_law(db, law_id)
    if not law:
        raise HTTPException(status_code=404, detail="法规不存在")

    updated = await LawService.update_law(db, law, data)
    return LawService._law_to_response(updated)


@router.delete("/{law_id}")
async def delete_law(
    law_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserWithAccess = None,
):
    """删除法规"""
    law = await LawService.get_law(db, law_id)
    if not law:
        raise HTTPException(status_code=404, detail="法规不存在")

    await LawService.delete_law(db, law)
    return {"message": "法规已删除", "success": True}


@router.post("/{law_id}/sync")
async def sync_law_to_ragflow(
    law_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserWithAccess = None,
):
    """同步单个法规到RAGFlow"""
    law = await LawService.get_law(db, law_id)
    if not law:
        raise HTTPException(status_code=404, detail="法规不存在")

    success, err_msg = await LawService.sync_to_ragflow(db, law, owner_id=current_user.id)

    if success:
        return {
            "message": "同步成功",
            "success": True,
            "is_synced": "synced",
            "ragflow_document_id": law.ragflow_document_id,
        }
    else:
        raise HTTPException(status_code=500, detail=err_msg or "同步失败，请检查RAGFlow配置")


@router.post("/{law_id}/templates", response_model=LawTemplateRelationResponse)
async def link_template_to_law(
    law_id: str,
    data: LawTemplateRelationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserWithAccess = None,
):
    """关联模板到法规"""
    law = await LawService.get_law(db, law_id)
    if not law:
        raise HTTPException(status_code=404, detail="法规不存在")

    relation = await LawService.link_template(db, law, data)
    return LawTemplateRelationResponse.model_validate(relation)


@router.get("/{law_id}/templates")
async def get_law_templates(
    law_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserWithAccess = None,
):
    """获取法规关联的所有模板"""
    law = await LawService.get_law(db, law_id)
    if not law:
        raise HTTPException(status_code=404, detail="法规不存在")

    templates = await LawService.get_law_templates(db, law_id)
    return {"templates": templates, "total": len(templates)}


@router.delete("/{law_id}/templates/{template_id}")
async def unlink_template_from_law(
    law_id: str,
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserWithAccess = None,
):
    """取消关联模板"""
    law = await LawService.get_law(db, law_id)
    if not law:
        raise HTTPException(status_code=404, detail="法规不存在")

    success = await LawService.unlink_template(db, law, template_id)
    if success:
        return {"message": "已取消关联", "success": True}
    else:
        raise HTTPException(status_code=404, detail="关联关系不存在")
