"""Pydantic schemas for extensions module."""

from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ============== Auth Schemas ==============


class LoginRequest(BaseModel):
    """Login request schema."""

    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    """Login response schema."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    """Refresh token request schema."""

    refresh_token: str


class TokenPayload(BaseModel):
    """Token payload schema."""

    sub: str  # user_id
    username: str
    role: str | None = None
    permissions: list[str] = []
    exp: int | None = None


class CurrentUser(BaseModel):
    """Current user schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    email: str
    full_name: str | None = None
    role_id: UUID | None = None
    role_name: str | None = None
    dept_id: UUID | None = None
    dept_name: str | None = None
    status: str


# ============== User Schemas ==============


class UserBase(BaseModel):
    """User base schema."""

    username: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    full_name: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=20)
    emp_no: str | None = Field(None, max_length=50)
    hire_date: date | None = None


class UserCreate(UserBase):
    """User create schema."""

    password: str = Field(..., min_length=6, max_length=100)
    dept_id: UUID | None = None
    role_id: UUID | None = None
    dept_ids: list[UUID] | None = None


class UserUpdate(BaseModel):
    """User update schema."""

    email: EmailStr | None = None
    full_name: str | None = Field(None, max_length=255)
    dept_id: UUID | None = None
    role_id: UUID | None = None
    status: str | None = None
    phone: str | None = Field(None, max_length=20)
    emp_no: str | None = Field(None, max_length=50)
    hire_date: date | None = None
    is_deleted: bool | None = None
    dept_ids: list[UUID] | None = None


class UserResponse(UserBase):
    """User response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dept_id: UUID | None = None
    dept_name: str | None = None
    dept_ids: list[UUID] = []
    primary_dept_id: UUID | None = None
    role_id: UUID | None = None
    role_name: str | None = None
    status: str
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    """User list response schema."""

    users: list[UserResponse]
    total: int


class UserPasswordChange(BaseModel):
    """User password change schema."""

    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=100)


class UserPasswordReset(BaseModel):
    """Admin password reset schema."""

    new_password: str = Field(..., min_length=6, max_length=100)


class UserSearchParams(BaseModel):
    """User search parameters."""

    keyword: str | None = Field(None, description="Search keyword for username, email, full_name")
    dept_id: UUID | None = None
    role_id: UUID | None = None
    status: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None


class UserBatchOperation(BaseModel):
    """User batch operation schema."""

    user_ids: list[UUID] = Field(..., min_length=1, max_length=100)
    operation: str = Field(..., pattern="^(enable|disable|delete)$")


class UserBatchResponse(BaseModel):
    """User batch operation response."""

    success: list[UUID]
    failed: list[dict]  # [{"id": UUID, "error": str}]


class UserStatistics(BaseModel):
    """User statistics schema."""

    total: int
    active: int
    inactive: int
    by_department: dict[str, int]
    by_role: dict[str, int]


# ============== Role Schemas ==============


class RoleBase(BaseModel):
    """Role base schema."""

    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=50)
    description: str | None = None
    level: int = 10
    parent_role_id: UUID | None = None


class RoleCreate(RoleBase):
    """Role create schema."""

    permissions: list[str] = []


class RoleUpdate(BaseModel):
    """Role update schema."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    permissions: list[str] | None = None
    level: int | None = None
    parent_role_id: UUID | None = None


class RoleResponse(RoleBase):
    """Role response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    permissions: list[str]
    is_system: bool
    parent_role_name: str | None = None
    created_at: datetime


class RoleListResponse(BaseModel):
    """Role list response schema."""

    roles: list[RoleResponse]
    total: int


class RoleCopy(BaseModel):
    """Role copy schema."""

    new_name: str = Field(..., min_length=1, max_length=100)
    new_code: str = Field(..., min_length=1, max_length=50)


class RoleAssignmentInfo(BaseModel):
    """Role assignment information."""

    role_id: UUID
    role_name: str
    user_count: int
    permissions: list[str]


# ============== Department Schemas ==============


class DepartmentBase(BaseModel):
    """Department base schema."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    parent_id: UUID | None = None
    leader_id: UUID | None = None
    sort_order: int = 0
    code: str | None = Field(None, max_length=50)
    status: str = "active"


class DepartmentCreate(DepartmentBase):
    """Department create schema."""


class DepartmentUpdate(BaseModel):
    """Department update schema."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    parent_id: UUID | None = None
    leader_id: UUID | None = None
    sort_order: int | None = None
    code: str | None = Field(None, max_length=50)
    status: str | None = None


class DepartmentResponse(DepartmentBase):
    """Department response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    leader_name: str | None = None
    created_at: datetime


class DepartmentTreeResponse(DepartmentResponse):
    """Department tree response schema."""

    children: list["DepartmentTreeResponse"] = []


class DepartmentListResponse(BaseModel):
    """Department list response schema."""

    departments: list[DepartmentTreeResponse]
    total: int


class DepartmentMove(BaseModel):
    """Department move schema."""

    new_parent_id: UUID | None = Field(None, description="New parent department ID, null means root")


class DepartmentBatchMove(BaseModel):
    """Department batch move users schema."""

    user_ids: list[UUID] = Field(..., min_length=1, max_length=100)


class DepartmentStatistics(BaseModel):
    """Department statistics schema."""

    total: int
    with_leader: int
    without_leader: int
    user_count: dict[str, int]  # {dept_id: user_count}


class DepartmentUsersResponse(BaseModel):
    """Department users response schema."""

    department: DepartmentResponse
    users: list[UserResponse]
    total: int


# ============== Knowledge Base Schemas ==============


_KB_TYPE_VALUES = frozenset({"ragflow", "pageindex"})


class KnowledgeBaseBase(BaseModel):
    """Knowledge base base schema."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    access_type: str = "private"
    kb_type: str = "ragflow"
    allowed_depts: list[UUID] | None = None
    embedding_model: str | None = None
    chunk_method: str = "naive"

    @field_validator("kb_type")
    @classmethod
    def validate_kb_type(cls, v: str) -> str:
        if v not in _KB_TYPE_VALUES:
            raise ValueError(f"kb_type must be one of {sorted(_KB_TYPE_VALUES)}")
        return v


class KnowledgeBaseCreate(KnowledgeBaseBase):
    """Knowledge base create schema."""


class KnowledgeBaseUpdate(BaseModel):
    """Knowledge base update schema."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    access_type: str | None = None
    kb_type: str | None = None
    allowed_depts: list[UUID] | None = None
    embedding_model: str | None = None
    chunk_method: str | None = None

    @field_validator("kb_type")
    @classmethod
    def validate_kb_type_optional(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in _KB_TYPE_VALUES:
            raise ValueError(f"kb_type must be one of {sorted(_KB_TYPE_VALUES)}")
        return v


class KnowledgeBaseResponse(KnowledgeBaseBase):
    """Knowledge base response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ragflow_dataset_id: str | None = None
    owner_id: UUID
    owner_name: str | None = None
    status: str
    created_at: datetime


class KnowledgeBaseListResponse(BaseModel):
    """Knowledge base list response schema."""

    knowledge_bases: list[KnowledgeBaseResponse]
    total: int


# ============== Document Schemas ==============


class DocumentStatus(str, Enum):
    """文档状态枚举，与 RAGFlow 解析状态统一映射。"""

    PENDING = "pending"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    DONE = "done"
    COMPLETED = "completed"
    PARSED = "parsed"
    ONE = "1"


def to_doc_status(raw: str | None) -> str:
    """将 RAGFlow 或后端任意合法 status 值映射为统一的 DocumentStatus 值。"""
    if not raw:
        return DocumentStatus.PENDING.value
    s = str(raw).lower().strip()
    mapping = {
        "1": DocumentStatus.SUCCESS.value,
        "done": DocumentStatus.DONE.value,
        "completed": DocumentStatus.COMPLETED.value,
        "parsed": DocumentStatus.PARSED.value,
        "success": DocumentStatus.SUCCESS.value,
        "fail": DocumentStatus.FAILED.value,
        "failed": DocumentStatus.FAILED.value,
        "uploading": DocumentStatus.UPLOADING.value,
        "processing": DocumentStatus.PROCESSING.value,
    }
    return mapping.get(s, DocumentStatus.PENDING.value)


def is_doc_ready(raw: str | None) -> bool:
    """判断文档是否已完成解析，可供抽取等下游操作使用。"""
    return to_doc_status(raw) in (
        DocumentStatus.SUCCESS.value,
        DocumentStatus.DONE.value,
        DocumentStatus.COMPLETED.value,
        DocumentStatus.PARSED.value,
    )


class DocumentResponse(BaseModel):
    """Document response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    knowledge_base_id: UUID
    name: str
    file_path: str
    file_size: int
    file_type: str | None = None
    ragflow_document_id: str | None = None
    status: str
    error_message: str | None = None
    created_at: datetime


class DocumentListResponse(BaseModel):
    """Document list response schema."""

    documents: list[DocumentResponse]
    total: int


class RAGChatRequest(BaseModel):
    """RAG chat request schema."""

    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    similarity_threshold: float = Field(default=0.2, ge=0.0, le=1.0)
    vector_similarity_weight: float = Field(default=0.3, ge=0.0, le=1.0)


class RAGChatResponse(BaseModel):
    """RAG chat response schema."""

    answer: str
    sources: list[dict] = []


class RAGFederatedSearchRequest(BaseModel):
    """Federated RAG search across multiple knowledge bases."""

    kb_ids: list[UUID] = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=6, ge=1, le=50)
    per_kb_k: int = Field(default=3, ge=1, le=20)


class RAGFederatedSearchResponse(BaseModel):
    """Federated RAG search response."""

    sources: list[dict] = []


# ============== Common Schemas ==============


class MessageResponse(BaseModel):
    """Message response schema."""

    message: str
    success: bool = True


class ErrorResponse(BaseModel):
    """Error response schema."""

    detail: str
    code: str | None = None


# ============== Conversation Schemas ==============


class ConversationCreate(BaseModel):
    """Conversation create schema."""

    title: str | None = Field(None, max_length=255)
    thread_id: str | None = Field(None, description="Use this thread_id (e.g. from LangGraph); if omitted, server generates one.")


class ConversationUpdate(BaseModel):
    """Conversation update schema."""

    title: str | None = Field(None, max_length=255)
    status: str | None = None


class ConversationResponse(BaseModel):
    """Conversation response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    thread_id: str
    user_id: UUID
    title: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    """Conversation list response schema."""

    conversations: list[ConversationResponse]
    total: int


# ============== AI Document Schemas ==============


class AIDocumentCreate(BaseModel):
    """AI document create schema."""

    title: str = Field(..., min_length=1, max_length=255)
    content: str | None = None
    folder: str = Field(default="默认文件夹", max_length=255)
    source_thread_id: str | None = Field(None, max_length=100)


class AIDocumentUpdate(BaseModel):
    """AI document update schema."""

    title: str | None = Field(None, min_length=1, max_length=255)
    content: str | None = None
    folder: str | None = Field(None, max_length=255)
    is_starred: bool | None = None
    is_shared: bool | None = None
    status: str | None = None


class AIDocumentResponse(BaseModel):
    """AI document response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    source_thread_id: str | None = None
    title: str
    content: str | None = None
    folder: str
    is_starred: bool
    is_shared: bool
    status: str
    created_at: datetime
    updated_at: datetime


class AIDocumentListResponse(BaseModel):
    """AI document list response schema."""

    documents: list[AIDocumentResponse]
    total: int


class FolderListResponse(BaseModel):
    """Folder list response schema."""

    folders: list[str]
