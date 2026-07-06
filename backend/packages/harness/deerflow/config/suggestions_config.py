# [EAI-ADD] suggestions config model — upstream commit d2cc991d backport
# 用途：控制对话结束后建议标签（follow-up suggestion chips）功能开关
# 上游 commit: d2cc991d ("make ai follow-up suggestions optional (#3591)")
# 差分标记：此文件为 EAI 从 upstream 手动 backport，非上游原生文件

from pydantic import BaseModel, Field


class SuggestionsConfig(BaseModel):
    """Configuration for automatic follow-up suggestions."""

    enabled: bool = Field(default=True, description="是否启用对话结束后建议标签生成")
