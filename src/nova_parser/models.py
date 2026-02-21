"""構造化抽出用の Pydantic モデル定義。"""

from __future__ import annotations

from pydantic import BaseModel


class Organization(BaseModel):
    """組織データ"""

    name: str
    """名称"""
    classification: str
    """分類（行政、企業など）"""
    sub_organizations: list[str]
    """下部組織"""
    headquarters: str
    """本部"""
    description: str
    """解説テキスト"""


class Skill(BaseModel):
    """技能・特技データ"""

    name: str
    """技能名"""
    ruby: str
    """ふりがな"""
    prerequisite: str
    """技能（前提技能）"""
    max_level: int | None
    """上限"""
    timing: str
    """タイミング"""
    target: str
    """対象"""
    range: str
    """射程"""
    target_value: str
    """目標値"""
    opposed: str
    """対決"""
    description: str
    """解説"""


class Equipment(BaseModel):
    """装備データ（防具・武器・アイテム等）"""

    name: str
    """装備名"""
    ruby: str
    """ふりがな"""
    category: str
    """カテゴリ（所属組織等）"""
    type: str
    """タイプ（ボディアーマー、ソーシャル等）"""
    purchase: str
    """購入価格（例: -/25）"""
    concealment: str
    """隠匿（例: 3/-1）"""
    defense_s: int | None
    """防御力(S)"""
    defense_p: int | None
    """防御力(P)"""
    defense_i: int | None
    """防御力(I)"""
    restriction: int | None
    """制"""
    electric_restriction: int | None
    """電制"""
    slot: str
    """部位"""
    description: str
    """解説"""


class RuleText(BaseModel):
    """ルール説明文"""

    title: str
    """見出し"""
    body: str
    """本文"""
    sub_sections: list[RuleText]
    """子セクション"""


class PageExtraction(BaseModel):
    """1ページから抽出された全データ"""

    source_file: str
    organizations: list[Organization]
    skills: list[Skill]
    equipment: list[Equipment]
    rules: list[RuleText]
