"""nova_parser.models の Pydantic モデルに対する単体テスト。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nova_parser.models import (
    Equipment,
    Organization,
    PageExtraction,
    RuleText,
    Skill,
)


def _make_skill(**overrides):
    """Skill の必須フィールドを埋めたデフォルト dict を返す。"""
    base = {
        "name": "プログラム",
        "ruby": "ぷろぐらむ",
        "prerequisite": "なし",
        "max_level": 5,
        "timing": "メジャー",
        "target": "単体",
        "range": "視認",
        "target_value": "技術-1",
        "opposed": "なし",
        "description": "プログラム作成判定を行う。",
    }
    base.update(overrides)
    return base


def _make_equipment(**overrides):
    base = {
        "name": "ナノマシン強化外骨格",
        "ruby": "なのましんきょうかがいこっかく",
        "category": "戦闘",
        "type": "ボディアーマー",
        "purchase": "-/25",
        "concealment": "3/-1",
        "defense_s": 4,
        "defense_p": 3,
        "defense_i": 2,
        "restriction": 1,
        "electric_restriction": 0,
        "slot": "胴",
        "description": "テスト用装備。",
    }
    base.update(overrides)
    return base


# AC M-01
def test_organization_can_be_constructed_with_all_fields():
    org = Organization(
        name="ノヴァ研究所",
        classification="企業",
        sub_organizations=["第一研究室", "第二研究室"],
        headquarters="東京",
        description="ノヴァ研究を行う架空組織。",
    )
    assert org.name == "ノヴァ研究所"
    assert org.classification == "企業"
    assert org.sub_organizations == ["第一研究室", "第二研究室"]
    assert org.headquarters == "東京"
    assert org.description == "ノヴァ研究を行う架空組織。"


# AC M-02
def test_skill_max_level_accepts_none():
    skill = Skill(**_make_skill(max_level=None))
    assert skill.max_level is None


def test_skill_max_level_accepts_integer():
    skill = Skill(**_make_skill(max_level=7))
    assert skill.max_level == 7


# AC M-03
@pytest.mark.parametrize(
    "field",
    ["defense_s", "defense_p", "defense_i", "restriction", "electric_restriction"],
)
def test_equipment_numeric_fields_accept_none(field):
    eq = Equipment(**_make_equipment(**{field: None}))
    assert getattr(eq, field) is None


# AC M-04
def test_organization_missing_required_field_raises_validation_error():
    with pytest.raises(ValidationError) as excinfo:
        Organization(
            classification="企業",
            sub_organizations=[],
            headquarters="東京",
            description="名称欠落",
        )  # type: ignore[call-arg]
    # 欠落フィールドが name であることを確認
    locs = [err["loc"] for err in excinfo.value.errors()]
    assert ("name",) in locs


def test_skill_missing_max_level_raises_validation_error():
    """max_level は int | None だが、デフォルト値が無いので未指定はエラー。"""
    payload = _make_skill()
    del payload["max_level"]
    with pytest.raises(ValidationError) as excinfo:
        Skill(**payload)
    locs = [err["loc"] for err in excinfo.value.errors()]
    assert ("max_level",) in locs


# AC M-05
@pytest.mark.parametrize("bad_value", ["abc", "三", "1.5.0", "not-a-number"])
def test_skill_max_level_rejects_non_numeric_string(bad_value):
    with pytest.raises(ValidationError):
        Skill(**_make_skill(max_level=bad_value))


@pytest.mark.parametrize("bad_value", ["abc", "三", "x"])
def test_equipment_defense_rejects_non_numeric_string(bad_value):
    with pytest.raises(ValidationError):
        Equipment(**_make_equipment(defense_s=bad_value))


# AC M-06
def test_rule_text_supports_recursive_nested_sub_sections():
    leaf = RuleText(title="孫見出し", body="孫本文", sub_sections=[])
    child = RuleText(title="子見出し", body="子本文", sub_sections=[leaf])
    root = RuleText(title="親見出し", body="親本文", sub_sections=[child])

    assert root.sub_sections[0].title == "子見出し"
    assert root.sub_sections[0].sub_sections[0].title == "孫見出し"
    assert root.sub_sections[0].sub_sections[0].sub_sections == []


def test_rule_text_sub_sections_rejects_non_rule_text_object():
    with pytest.raises(ValidationError):
        RuleText(
            title="親",
            body="本文",
            sub_sections=["not-a-rule-text"],  # type: ignore[list-item]
        )


# AC M-07
def test_page_extraction_round_trip_via_model_dump_and_validate():
    original = PageExtraction(
        source_file="page-001.png",
        organizations=[
            Organization(
                name="ノヴァ研究所",
                classification="企業",
                sub_organizations=["第一研究室"],
                headquarters="東京",
                description="解説",
            )
        ],
        skills=[Skill(**_make_skill())],
        equipment=[Equipment(**_make_equipment())],
        rules=[
            RuleText(
                title="ルール",
                body="本文",
                sub_sections=[RuleText(title="子", body="子本文", sub_sections=[])],
            )
        ],
    )

    dumped = original.model_dump()
    rebuilt = PageExtraction.model_validate(dumped)

    assert rebuilt == original
    assert rebuilt.model_dump() == dumped


# AC M-08
@pytest.mark.parametrize(
    "missing_field",
    ["source_file", "organizations", "skills", "equipment", "rules"],
)
def test_page_extraction_list_fields_are_required(missing_field):
    payload = {
        "source_file": "page-001.png",
        "organizations": [],
        "skills": [],
        "equipment": [],
        "rules": [],
    }
    del payload[missing_field]
    with pytest.raises(ValidationError) as excinfo:
        PageExtraction(**payload)  # type: ignore[arg-type]
    locs = [err["loc"] for err in excinfo.value.errors()]
    assert (missing_field,) in locs
