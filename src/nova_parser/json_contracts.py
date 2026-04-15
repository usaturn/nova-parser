"""Gemini JSON 出力のスキーマ定義と軽量バリデータ。"""

from __future__ import annotations


def _string_object_schema(*, additional_properties: bool | dict = False) -> dict:
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": additional_properties,
    }


def _dynamic_string_item_schema() -> dict:
    return _string_object_schema(additional_properties={"type": "string"})


def build_gamedata_result_schema() -> dict:
    """動的ゲームデータ抽出のトップレベル形状を拘束する JSON Schema。"""
    type_schema = {
        "type": "object",
        "properties": {
            "type_name": {"type": "string"},
            "items": {
                "type": "array",
                "items": _dynamic_string_item_schema(),
            },
        },
        "required": ["type_name", "items"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "types": {
                "type": "array",
                "items": type_schema,
            },
        },
        "required": ["types"],
        "additionalProperties": False,
    }


def build_extract_result_schema(schema: dict) -> dict:
    """extract モード用の JSON Schema を構築する。"""
    matched_type_schemas = []
    for type_data in schema["types"]:
        fields = list(type_data["fields"])
        matched_type_schemas.append(
            {
                "type": "object",
                "properties": {
                    "type_name": {"type": "string", "enum": [type_data["type_name"]]},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {field: {"type": "string"} for field in fields},
                            "required": fields,
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["type_name", "items"],
                "additionalProperties": False,
            }
        )

    unmatched_type_schema = {
        "type": "object",
        "properties": {
            "type_name": {"type": "string"},
            "items": {
                "type": "array",
                "items": _dynamic_string_item_schema(),
            },
        },
        "required": ["type_name", "items"],
        "additionalProperties": False,
    }

    return {
        "type": "object",
        "properties": {
            "matched_types": {
                "type": "array",
                "items": {"anyOf": matched_type_schemas} if matched_type_schemas else unmatched_type_schema,
            },
            "unmatched_types": {
                "type": "array",
                "items": unmatched_type_schema,
            },
        },
        "required": ["matched_types", "unmatched_types"],
        "additionalProperties": False,
    }


def _validate_dynamic_item(item: object, *, path: str) -> None:
    if not isinstance(item, dict):
        msg = f"{path} が object ではありません。"
        raise ValueError(msg)
    for key, value in item.items():
        if not isinstance(key, str):
            msg = f"{path} のキーが文字列ではありません。"
            raise ValueError(msg)
        if not isinstance(value, str):
            msg = f"{path}.{key} が文字列ではありません。"
            raise ValueError(msg)


def validate_gamedata_result(result: dict | list) -> None:
    """動的ゲームデータ抽出結果の最小形状を検証する。"""
    if not isinstance(result, dict):
        msg = "トップレベル JSON が object ではありません。"
        raise ValueError(msg)
    types = result.get("types")
    if not isinstance(types, list):
        msg = "types が配列ではありません。"
        raise ValueError(msg)
    for index, type_data in enumerate(types):
        path = f"types[{index}]"
        if not isinstance(type_data, dict):
            msg = f"{path} が object ではありません。"
            raise ValueError(msg)
        if not isinstance(type_data.get("type_name"), str):
            msg = f"{path}.type_name が文字列ではありません。"
            raise ValueError(msg)
        items = type_data.get("items")
        if not isinstance(items, list):
            msg = f"{path}.items が配列ではありません。"
            raise ValueError(msg)
        for item_index, item in enumerate(items):
            _validate_dynamic_item(item, path=f"{path}.items[{item_index}]")


def validate_extract_result(result: dict | list, schema: dict) -> None:
    """extract モードの結果がスキーマと一致しているか検証する。"""
    if not isinstance(result, dict):
        msg = "トップレベル JSON が object ではありません。"
        raise ValueError(msg)

    schema_fields = {type_data["type_name"]: list(type_data["fields"]) for type_data in schema["types"]}

    matched_types = result.get("matched_types")
    if not isinstance(matched_types, list):
        msg = "matched_types が配列ではありません。"
        raise ValueError(msg)
    for type_index, type_data in enumerate(matched_types):
        path = f"matched_types[{type_index}]"
        if not isinstance(type_data, dict):
            msg = f"{path} が object ではありません。"
            raise ValueError(msg)
        type_name = type_data.get("type_name")
        if not isinstance(type_name, str):
            msg = f"{path}.type_name が文字列ではありません。"
            raise ValueError(msg)
        if type_name not in schema_fields:
            msg = f"{path}.type_name が既知の型ではありません: {type_name}"
            raise ValueError(msg)

        items = type_data.get("items")
        if not isinstance(items, list):
            msg = f"{path}.items が配列ではありません。"
            raise ValueError(msg)

        expected_fields = schema_fields[type_name]
        expected_field_set = set(expected_fields)
        for item_index, item in enumerate(items):
            item_path = f"{path}.items[{item_index}]"
            if not isinstance(item, dict):
                msg = f"{item_path} が object ではありません。"
                raise ValueError(msg)
            if set(item) != expected_field_set:
                msg = f"{item_path} のフィールドがスキーマ定義と一致しません。"
                raise ValueError(msg)
            for field in expected_fields:
                value = item.get(field)
                if not isinstance(value, str):
                    msg = f"{item_path}.{field} が文字列ではありません。"
                    raise ValueError(msg)

    unmatched_types = result.get("unmatched_types")
    if not isinstance(unmatched_types, list):
        msg = "unmatched_types が配列ではありません。"
        raise ValueError(msg)
    for type_index, type_data in enumerate(unmatched_types):
        path = f"unmatched_types[{type_index}]"
        if not isinstance(type_data, dict):
            msg = f"{path} が object ではありません。"
            raise ValueError(msg)
        if not isinstance(type_data.get("type_name"), str):
            msg = f"{path}.type_name が文字列ではありません。"
            raise ValueError(msg)
        items = type_data.get("items")
        if not isinstance(items, list):
            msg = f"{path}.items が配列ではありません。"
            raise ValueError(msg)
        for item_index, item in enumerate(items):
            _validate_dynamic_item(item, path=f"{path}.items[{item_index}]")
