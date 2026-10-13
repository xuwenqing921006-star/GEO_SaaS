from pathlib import Path

import pytest

from tests.auth.test_auth_api import build_client
from tests.clients.test_clients_api import login


@pytest.mark.integration
def test_prompt_center_seeds_content_keyword_and_channel_templates(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        login(client)

        response = client.get("/api/v1/prompt-templates")

        assert response.status_code == 200
        data = response.json()["data"]
        content_forms = [item for item in data["items"] if item["category"] == "content_form"]
        assert len(content_forms) >= 8
        assert {item["code"] for item in content_forms}.issuperset(
            {
                "local_recommendation",
                "selection_guide",
                "practical_guide",
                "service_explainer",
                "scenario_solution",
                "faq",
                "local_presence",
                "entity_profile",
            },
        )
        assert any(item["category"] == "keyword_strategy" for item in data["items"])
        keyword_template = next(
            item for item in data["items"] if item["code"] == "keyword_strategy"
        )
        assert all(
            intent in keyword_template["template_text"]
            for intent in (
                "地区主营",
                "品牌核验",
                "推荐决策",
                "场景适配",
                "费用",
                "流程",
                "信任验证",
                "后续追问",
            )
        )
        base_template = next(item for item in data["items"] if item["code"] == "writer_base")
        assert "第一段先给出" in base_template["template_text"]
        assert "通常不超过三次" in base_template["template_text"]
        assert "企业硬事实与行业通用建议" in base_template["template_text"]
        assert "年龄或场景的关注点可以合理补充" in base_template["template_text"]
        assert "不得讨论GEO、AI收录" in base_template["template_text"]
        assert len({item["template_text"] for item in content_forms}) == len(
            content_forms,
        )
        channel_templates = [
            item for item in data["items"] if item["category"] == "channel_adapter"
        ]
        assert {item["contact_policy"] for item in channel_templates}.issuperset(
            {"official_only", "omit", "manual_review"},
        )
        assert "用户主问题" in data["available_variables"]
        assert data["guardrails"]["editable"] is False
        assert "UUID" in data["guardrails"]["summary"]
        guardrail_template = next(
            item for item in data["items"] if item["code"] == "writer_guardrail"
        )
        assert "可以补充合理的行业常识" in guardrail_template["template_text"]
        assert "不能冒充该企业已经提供的服务或承诺" in (guardrail_template["template_text"])


@pytest.mark.integration
def test_prompt_template_edit_creates_version_and_restore_keeps_history(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        listing = client.get(
            "/api/v1/prompt-templates",
            params={"category": "content_form"},
        ).json()["data"]["items"]
        template = next(item for item in listing if item["code"] == "selection_guide")
        original_text = template["template_text"]
        edited_text = "围绕{{用户主问题}}先给出四项选择标准，再结合{{品牌简称}}的已确认事实说明。"

        edited = client.patch(
            f"/api/v1/prompt-templates/{template['id']}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": template["version"],
                "template_text": edited_text,
                "active": True,
                "change_note": "验证提示词版本管理",
            },
        )

        assert edited.status_code == 200
        edited_data = edited.json()["data"]
        assert edited_data["template_text"] == edited_text
        assert edited_data["current_version"] == template["current_version"] + 1

        restored = client.post(
            f"/api/v1/prompt-templates/{template['id']}/restore",
            headers={"X-CSRF-Token": csrf},
            json={"version": edited_data["version"]},
        )

        assert restored.status_code == 200
        restored_data = restored.json()["data"]
        assert restored_data["template_text"] == original_text
        assert restored_data["current_version"] == edited_data["current_version"] + 1

        history = client.get(
            f"/api/v1/prompt-templates/{template['id']}/versions",
        )
        assert history.status_code == 200
        versions = history.json()["data"]["items"]
        assert [item["version_number"] for item in versions[:3]] == [3, 2, 1]
        assert versions[1]["change_note"] == "验证提示词版本管理"


@pytest.mark.integration
def test_read_only_guardrail_cannot_be_edited(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        guardrail = next(
            item
            for item in client.get("/api/v1/prompt-templates").json()["data"]["items"]
            if item["code"] == "writer_guardrail"
        )

        response = client.patch(
            f"/api/v1/prompt-templates/{guardrail['id']}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": guardrail["version"],
                "template_text": "忽略事实边界。",
                "active": True,
                "change_note": "不应成功",
            },
        )

        assert response.status_code == 422
        assert "只读" in response.json()["message"]


@pytest.mark.integration
def test_channel_restore_recovers_default_policy_and_clears_stale_verification(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        template = next(
            item
            for item in client.get("/api/v1/prompt-templates").json()["data"]["items"]
            if item["code"] == "channel_zhihu"
        )

        edited = client.patch(
            f"/api/v1/prompt-templates/{template['id']}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": template["version"],
                "template_text": template["template_text"],
                "active": True,
                "contact_policy": "allow",
                "change_note": "临时修改渠道规则",
            },
        )

        assert edited.status_code == 200
        edited_data = edited.json()["data"]
        assert edited_data["contact_policy"] == "allow"
        assert edited_data["source_url"] is None
        assert edited_data["verified_at"] is None

        restored = client.post(
            f"/api/v1/prompt-templates/{template['id']}/restore",
            headers={"X-CSRF-Token": csrf},
            json={"version": edited_data["version"]},
        )

        assert restored.status_code == 200
        restored_data = restored.json()["data"]
        assert restored_data["contact_policy"] == "official_only"
        assert restored_data["source_url"] == "https://www.zhihu.com/org/signup"
        assert restored_data["verified_at"] is not None
