# ruff: noqa: RUF001

import pytest

from app.prompt_templates import PROMPT_SEEDS_BY_CODE
from app.publishing import PUBLISHING_PLATFORM_CATALOG
from app.publishing_specs import (
    PUBLISHING_PLATFORM_SPECS,
    platform_generation_instruction,
    platform_prompt_contract,
    required_uploaded_body_images,
)


@pytest.mark.unit
def test_every_automatic_publishing_platform_has_generation_rules() -> None:
    platform_ids = {item["id"] for item in PUBLISHING_PLATFORM_CATALOG}

    assert platform_ids == set(PUBLISHING_PLATFORM_SPECS)
    assert all(f"channel_{channel_id}" in PROMPT_SEEDS_BY_CODE for channel_id in platform_ids)


@pytest.mark.unit
def test_baijia_generation_spec_matches_live_cover_editor() -> None:
    spec = PUBLISHING_PLATFORM_SPECS["baijia"]
    contract = platform_prompt_contract("baijia")

    assert spec.title_min_characters == 2
    assert spec.title_max_characters == 64
    assert spec.image.cover_size == (1200, 800)
    assert spec.image.max_bytes == 5 * 1024 * 1024
    assert contract is not None
    assert contract["image_requirements"]["cover_width"] == 1200
    assert contract["image_requirements"]["cover_height"] == 800


@pytest.mark.unit
def test_sohu_generation_spec_requires_one_ready_body_image() -> None:
    spec = PUBLISHING_PLATFORM_SPECS["sohu"]

    assert spec.title_max_characters == 72
    assert spec.summary_max_characters == 120
    assert spec.image.minimum_body_images == 1
    assert spec.image.target_body_images == 1
    assert "450×300" in platform_generation_instruction("sohu")


@pytest.mark.unit
def test_netease_generation_spec_matches_current_article_publisher() -> None:
    spec = PUBLISHING_PLATFORM_SPECS["netease"]
    contract = platform_prompt_contract("netease")

    assert spec.title_min_characters == 5
    assert spec.title_max_characters == 64
    assert spec.image.cover_size == (1200, 900)
    assert spec.image.minimum_body_images == 3
    assert spec.image.target_body_images == 3
    assert spec.image.maximum_body_images == 3
    assert required_uploaded_body_images(spec) == 2
    assert contract is not None
    assert contract["image_requirements"]["minimum_body_images"] == 3
    assert "正文固定插入3张" in platform_generation_instruction("netease")
    assert "标题不得出现企业或品牌名称" in platform_generation_instruction("netease")
    assert "广告、软文、推广" in platform_generation_instruction("netease")
    assert "https://mp.163.com/college.html#/guidence/audit/regulations" in spec.source_urls


@pytest.mark.unit
def test_penguin_generation_spec_uses_body_images_as_cover_candidates() -> None:
    spec = PUBLISHING_PLATFORM_SPECS["penguin"]
    contract = platform_prompt_contract("penguin")

    assert spec.title_min_characters == 5
    assert spec.title_max_characters == 64
    assert spec.daily_publication_limit == 5
    assert spec.image.cover_size == (1200, 900)
    assert spec.image.cover_source == "body"
    assert spec.image.minimum_body_images == 2
    assert required_uploaded_body_images(spec) == 2
    assert contract is not None
    assert contract["daily_publication_limit"] == 5
    assert contract["image_requirements"]["cover_source"] == "body"
    instruction = platform_generation_instruction("penguin")
    assert "主动声明使用AI生成内容" in instruction
    assert "手机号、微信号、QQ号、二维码" in instruction


@pytest.mark.unit
def test_yidian_generation_spec_prevents_marketing_and_low_quality_content() -> None:
    spec = PUBLISHING_PLATFORM_SPECS["yidian"]
    contract = platform_prompt_contract("yidian")

    assert spec.title_min_characters == 5
    assert spec.generation_title_max_characters == 30
    assert spec.minimum_body_characters == 600
    assert spec.image.cover_size == (1200, 675)
    assert spec.image.minimum_body_images == 3
    assert spec.image.target_body_images == 3
    assert required_uploaded_body_images(spec) == 2
    assert contract is not None
    assert contract["image_requirements"]["minimum_body_images"] == 3
    instruction = platform_generation_instruction("yidian")
    assert "广告、营销" in instruction
    assert "手机号、微信、二维码、网址" in instruction
    assert "内容由AI生成" in instruction
    assert "不少于3张" in instruction
    assert "https://mp.yidianzixun.com/static/opsspecs.html" in spec.source_urls


@pytest.mark.unit
def test_platform_prompt_includes_content_and_image_contract() -> None:
    instruction = platform_generation_instruction("toutiao")

    assert "标题5—100字" in instruction
    assert "正文不少于600个有效字符" in instruction
    assert "1200×675生成封面" in instruction
    assert "图片" in instruction


@pytest.mark.unit
def test_toutiao_generation_spec_blocks_batch_low_quality_and_soft_ads() -> None:
    instruction = platform_generation_instruction("toutiao")
    contract = platform_prompt_contract("toutiao")

    assert "批量发布" in instruction
    assert "纯广告" in instruction
    assert "企业标准名称最多自然出现2次" in instruction
    assert "电话、微信、二维码" in instruction
    assert "至少3个" in instruction
    assert contract is not None
    assert contract["content_requirements"] == list(
        PUBLISHING_PLATFORM_SPECS["toutiao"].content_requirements,
    )
