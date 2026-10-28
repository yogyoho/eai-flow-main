"""Pydantic v2 schemas.

Designer payloads use warm-flow's camelCase wire names. Internal API models for
CRUD/runtime use snake_case, which matches the rest of eai-flow.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


def to_camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel, extra="allow")


# ---------------------------------------------------------------------------
# Designer JSON contract (warm-flow DTOs)
# ---------------------------------------------------------------------------


class SkipJson(CamelModel):
    id: int | None = None
    now_node_code: str | None = None
    now_node_type: int | None = None
    next_node_code: str | None = None
    next_node_type: int | None = None
    skip_name: str | None = None
    skip_type: str | None = "PASS"
    skip_condition: str | None = None
    coordinate: str | None = None
    status: int | None = None
    expr: str | None = None
    ext_map: dict[str, Any] = Field(default_factory=dict)
    prompt_content: list[str] = Field(default_factory=list)


class NodeJson(CamelModel):
    id: int | None = None
    node_type: int = 1
    node_code: str
    node_name: str | None = None
    permission_flag: str | None = None
    node_ratio: str | None = "0"
    coordinate: str | None = None
    any_node_skip: str | None = None
    listener_type: str | None = None
    listener_path: str | None = None
    form_custom: str = "N"
    form_path: str | None = None
    ext: str | None = None
    version: str | None = None
    status: int | None = None
    handler_type: str | None = None
    handler_path: str | None = None
    ext_map: dict[str, Any] = Field(default_factory=dict)
    prompt_content: dict[str, Any] | None = None
    skip_list: list[SkipJson] = Field(default_factory=list)


class DefJson(CamelModel):
    id: int | None = None
    flow_code: str
    flow_name: str
    model_value: str = "CLASSICS"
    category: str | None = None
    version: str | None = None
    is_publish: int | None = None
    form_custom: str = "N"
    form_path: str | None = None
    listener_type: str | None = None
    listener_path: str | None = None
    ext: str | None = None
    ext_map: dict[str, Any] = Field(default_factory=dict)
    instance: dict[str, Any] | None = None
    node_list: list[NodeJson] = Field(default_factory=list)
    chart_status_color: list[str] = Field(default_factory=list)
    top_text: str | None = None
    top_text_show: bool = False
    create_by: str | None = None
    update_by: str | None = None
    category_list: list[dict[str, Any]] = Field(default_factory=list)
    form_path_list: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("node_list", mode="before")
    @classmethod
    def _none_to_list(cls, value: Any) -> Any:
        return value or []


# ---------------------------------------------------------------------------
# Definition CRUD
# ---------------------------------------------------------------------------


class DefinitionCreate(BaseModel):
    flow_code: str = Field(min_length=1, max_length=40)
    flow_name: str = Field(min_length=1, max_length=100)
    category: str | None = None
    form_custom: str = "N"
    form_path: str | None = None
    listener_type: str | None = None
    listener_path: str | None = None
    ext: str | None = None


class DefinitionUpdate(BaseModel):
    flow_name: str | None = None
    category: str | None = None
    form_custom: str | None = None
    form_path: str | None = None
    listener_type: str | None = None
    listener_path: str | None = None
    ext: str | None = None


class DefinitionImport(BaseModel):
    payload: dict[str, Any]


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------


class StartInstanceRequest(BaseModel):
    flow_code: str
    business_id: str = ""
    handler: str = "system"
    variables: dict[str, Any] = Field(default_factory=dict)
    flow_status: str | None = None
    ext: str | None = None


class HandleTaskRequest(BaseModel):
    handler: str = "system"
    message: str = ""
    skip_type: Literal["PASS", "REJECT"] = "PASS"
    node_code: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)
    cooperate_type: int | None = None
    add_handlers: list[str] = Field(default_factory=list)
    reduce_handlers: list[str] = Field(default_factory=list)
    ignore: bool = False
    ignore_depute: bool = False
    ignore_cooperate: bool = False
    flow_status: str | None = None
    his_status: str | None = None
    ext: str | None = None


class TransferRequest(BaseModel):
    handler: str
    add_handlers: list[str]
    message: str = ""


class HandlerActionRequest(BaseModel):
    handler: str
    add_handlers: list[str] = Field(default_factory=list)
    reduce_handlers: list[str] = Field(default_factory=list)
    message: str = ""


class RevokeRequest(BaseModel):
    handler: str | None = None
    message: str = ""
    flow_status: str | None = None


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------


class FormCreate(BaseModel):
    form_code: str
    form_name: str
    form_type: int = 0
    form_content: str | None = None
    form_path: str | None = None
    ext: str | None = None


class FormUpdate(BaseModel):
    form_name: str | None = None
    form_type: int | None = None
    form_content: str | None = None
    form_path: str | None = None
    ext: str | None = None


class FormContentRequest(BaseModel):
    id: int | None = None
    form_content: str | None = None
    form: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Generic responses
# ---------------------------------------------------------------------------

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int


class ApiMessage(BaseModel):
    message: str


class DefinitionOut(BaseModel):
    id: int
    flow_code: str
    flow_name: str
    model_value: str
    category: str | None
    version: str
    is_publish: int
    form_custom: str
    form_path: str | None
    activity_status: int
    listener_type: str | None
    listener_path: str | None
    ext: str | None
    create_time: datetime | None
    create_by: str
    update_time: datetime | None
    update_by: str
    tenant_id: str


class FormOut(BaseModel):
    id: int
    form_code: str
    form_name: str
    version: str
    is_publish: int
    form_type: int
    form_content: str | None
    form_path: str | None
    ext: str | None
    create_time: datetime | None
    update_time: datetime | None


class TaskOut(BaseModel):
    id: int
    definition_id: int
    instance_id: int
    node_code: str
    node_name: str | None
    node_type: int
    flow_status: str
    form_custom: str
    form_path: str | None
    create_time: datetime | None
    flow_name: str | None = None
    business_id: str | None = None
    assignees: list[str] = Field(default_factory=list)


class InstanceOut(BaseModel):
    id: int
    definition_id: int
    business_id: str
    node_type: int
    node_code: str
    node_name: str | None
    flow_status: str
    activity_status: int
    variable: dict[str, Any] = Field(default_factory=dict)
    def_json: dict[str, Any] | None = None
    create_time: datetime | None
    create_by: str
    update_time: datetime | None
    flow_name: str | None = None


class HisTaskOut(BaseModel):
    id: int
    definition_id: int
    instance_id: int
    task_id: int
    node_code: str | None
    node_name: str | None
    node_type: int | None
    target_node_code: str | None
    target_node_name: str | None
    approver: str | None
    cooperate_type: int
    collaborator: str | None
    skip_type: str
    flow_status: str
    message: str | None
    create_time: datetime | None
    update_time: datetime | None
