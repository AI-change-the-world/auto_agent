from enum import Enum
from typing import Any, Dict, List

import pytest
from httpx import AsyncClient

# 假设 app 已定义
from main import app

# 假设这些模型类已定义在 schemas 模块中
from schemas import (
    AddProjectMemberRequest,
    AddTaskTagRequest,
    CreateAttachmentRequest,
    CreateCommentRequest,
    CreateProjectRequest,
    CreateTagRequest,
    CreateTaskRequest,
    EmptyResponse,
    ProjectStatusEnum,
    TaskPriorityEnum,
    TaskStatusEnum,
    UpdateCommentRequest,
    UpdateProjectRequest,
    UpdateTagRequest,
    UpdateTaskRequest,
)


@pytest.fixture
async def client() -> AsyncClient:
    """提供测试客户端"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """提供认证头"""
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def sample_project_data() -> Dict[str, Any]:
    """提供示例项目数据"""
    return {
        "name": "Test Project",
        "description": "A test project",
        "status": ProjectStatusEnum.ACTIVE.value,
    }


@pytest.fixture
def sample_task_data() -> Dict[str, Any]:
    """提供示例任务数据"""
    return {
        "title": "Test Task",
        "description": "A test task",
        "priority": TaskPriorityEnum.MEDIUM.value,
        "status": TaskStatusEnum.TODO.value,
    }


@pytest.fixture
def sample_tag_data() -> Dict[str, Any]:
    """提供示例标签数据"""
    return {"name": "Test Tag", "color": "#FF0000"}


@pytest.fixture
def sample_comment_data() -> Dict[str, Any]:
    """提供示例评论数据"""
    return {"content": "This is a test comment"}


@pytest.fixture
def sample_attachment_data() -> Dict[str, Any]:
    """提供示例附件数据"""
    return {
        "filename": "test.txt",
        "file_url": "http://example.com/test.txt",
        "file_size": 1024,
    }


# ======================
# PROJECT ENDPOINT TESTS
# ======================


@pytest.mark.asyncio
async def test_get_projects_success(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试获取项目列表成功"""
    response = await client.get("/projects", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "size" in data


@pytest.mark.asyncio
async def test_get_projects_with_params(
    client: AsyncClient, auth_headers: Dict[str, str]
):
    """测试获取项目列表带参数"""
    params = {"page": 1, "size": 10, "status": ProjectStatusEnum.ACTIVE.value}
    response = await client.get("/projects", params=params, headers=auth_headers)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_projects_unauthorized(client: AsyncClient):
    """测试未认证获取项目列表"""
    response = await client.get("/projects")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_project_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
):
    """测试创建项目成功"""
    response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["name"] == sample_project_data["name"]
    assert data["status"] == sample_project_data["status"]


@pytest.mark.asyncio
async def test_create_project_validation_error(
    client: AsyncClient, auth_headers: Dict[str, str]
):
    """测试创建项目验证错误"""
    invalid_data = {"name": ""}  # 名称为空
    response = await client.post("/projects", json=invalid_data, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_project_success(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试获取单个项目成功"""
    # 先创建一个项目
    project_data = {"name": "Test Project", "status": ProjectStatusEnum.ACTIVE.value}
    create_response = await client.post(
        "/projects", json=project_data, headers=auth_headers
    )
    project_id = create_response.json()["id"]

    response = await client.get(f"/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == project_id


@pytest.mark.asyncio
async def test_get_project_not_found(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试获取不存在的项目"""
    response = await client.get("/projects/999999", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_project_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
):
    """测试更新项目成功"""
    # 先创建一个项目
    create_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    project_id = create_response.json()["id"]

    update_data = {
        "name": "Updated Project",
        "status": ProjectStatusEnum.COMPLETED.value,
    }
    response = await client.put(
        f"/projects/{project_id}", json=update_data, headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == update_data["name"]
    assert data["status"] == update_data["status"]


@pytest.mark.asyncio
async def test_delete_project_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
):
    """测试删除项目成功"""
    # 先创建一个项目
    create_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    project_id = create_response.json()["id"]

    response = await client.delete(f"/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data == {}


# ======================
# PROJECT MEMBERS TESTS
# ======================


@pytest.mark.asyncio
async def test_get_project_members_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
):
    """测试获取项目成员列表成功"""
    # 先创建一个项目
    create_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    project_id = create_response.json()["id"]

    response = await client.get(f"/projects/{project_id}/members", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_add_project_member_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
):
    """测试添加项目成员成功"""
    # 先创建一个项目
    create_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    project_id = create_response.json()["id"]

    member_data = {"user_id": 1, "role": "member"}
    response = await client.post(
        f"/projects/{project_id}/members", json=member_data, headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert "user_id" in data
    assert data["user_id"] == member_data["user_id"]


@pytest.mark.asyncio
async def test_remove_project_member_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
):
    """测试移除项目成员成功"""
    # 先创建一个项目并添加成员
    create_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    project_id = create_response.json()["id"]

    member_data = {"user_id": 1, "role": "member"}
    await client.post(
        f"/projects/{project_id}/members", json=member_data, headers=auth_headers
    )

    response = await client.delete(
        f"/projects/{project_id}/members/1", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data == {}


# ======================
# USER ENDPOINT TESTS
# ======================


@pytest.mark.asyncio
async def test_get_users_success(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试获取用户列表成功"""
    response = await client.get("/users", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_get_user_success(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试获取单个用户成功"""
    response = await client.get("/users/1", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "id" in data


# ======================
# TASK ENDPOINT TESTS
# ======================


@pytest.mark.asyncio
async def test_get_tasks_success(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试获取任务列表成功"""
    response = await client.get("/tasks", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_get_tasks_with_filters(
    client: AsyncClient, auth_headers: Dict[str, str]
):
    """测试获取任务列表带过滤参数"""
    params = {
        "project_id": 1,
        "status": TaskStatusEnum.TODO.value,
        "page": 1,
        "size": 10,
    }
    response = await client.get("/tasks", params=params, headers=auth_headers)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_create_task_success(
    client: AsyncClient, auth_headers: Dict[str, str], sample_task_data: Dict[str, Any]
):
    """测试创建任务成功"""
    response = await client.post("/tasks", json=sample_task_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["title"] == sample_task_data["title"]


@pytest.mark.asyncio
async def test_get_task_success(
    client: AsyncClient, auth_headers: Dict[str, str], sample_task_data: Dict[str, Any]
):
    """测试获取单个任务成功"""
    create_response = await client.post(
        "/tasks", json=sample_task_data, headers=auth_headers
    )
    task_id = create_response.json()["id"]

    response = await client.get(f"/tasks/{task_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == task_id


@pytest.mark.asyncio
async def test_update_task_success(
    client: AsyncClient, auth_headers: Dict[str, str], sample_task_data: Dict[str, Any]
):
    """测试更新任务成功"""
    create_response = await client.post(
        "/tasks", json=sample_task_data, headers=auth_headers
    )
    task_id = create_response.json()["id"]

    update_data = {"title": "Updated Task", "status": TaskStatusEnum.IN_PROGRESS.value}
    response = await client.put(
        f"/tasks/{task_id}", json=update_data, headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == update_data["title"]
    assert data["status"] == update_data["status"]


@pytest.mark.asyncio
async def test_delete_task_success(
    client: AsyncClient, auth_headers: Dict[str, str], sample_task_data: Dict[str, Any]
):
    """测试删除任务成功"""
    create_response = await client.post(
        "/tasks", json=sample_task_data, headers=auth_headers
    )
    task_id = create_response.json()["id"]

    response = await client.delete(f"/tasks/{task_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data == {}


@pytest.mark.asyncio
async def test_get_subtasks_success(
    client: AsyncClient, auth_headers: Dict[str, str], sample_task_data: Dict[str, Any]
):
    """测试获取子任务列表成功"""
    # 创建父任务
    parent_response = await client.post(
        "/tasks", json=sample_task_data, headers=auth_headers
    )
    parent_task_id = parent_response.json()["id"]

    response = await client.get(
        f"/tasks/{parent_task_id}/subtasks", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


# ======================
# TAG ENDPOINT TESTS
# ======================


@pytest.mark.asyncio
async def test_get_tags_success(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试获取标签列表成功"""
    response = await client.get("/tags", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_create_tag_success(
    client: AsyncClient, auth_headers: Dict[str, str], sample_tag_data: Dict[str, Any]
):
    """测试创建标签成功"""
    response = await client.post("/tags", json=sample_tag_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["name"] == sample_tag_data["name"]


@pytest.mark.asyncio
async def test_get_tag_success(
    client: AsyncClient, auth_headers: Dict[str, str], sample_tag_data: Dict[str, Any]
):
    """测试获取单个标签成功"""
    create_response = await client.post(
        "/tags", json=sample_tag_data, headers=auth_headers
    )
    tag_id = create_response.json()["id"]

    response = await client.get(f"/tags/{tag_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == tag_id


@pytest.mark.asyncio
async def test_update_tag_success(
    client: AsyncClient, auth_headers: Dict[str, str], sample_tag_data: Dict[str, Any]
):
    """测试更新标签成功"""
    create_response = await client.post(
        "/tags", json=sample_tag_data, headers=auth_headers
    )
    tag_id = create_response.json()["id"]

    update_data = {"name": "Updated Tag", "color": "#00FF00"}
    response = await client.put(
        f"/tags/{tag_id}", json=update_data, headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == update_data["name"]
    assert data["color"] == update_data["color"]


@pytest.mark.asyncio
async def test_delete_tag_success(
    client: AsyncClient, auth_headers: Dict[str, str], sample_tag_data: Dict[str, Any]
):
    """测试删除标签成功"""
    create_response = await client.post(
        "/tags", json=sample_tag_data, headers=auth_headers
    )
    tag_id = create_response.json()["id"]

    response = await client.delete(f"/tags/{tag_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data == {}


# ======================
# TASK TAGS TESTS
# ======================


@pytest.mark.asyncio
async def test_get_task_tags_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_task_data: Dict[str, Any],
    sample_tag_data: Dict[str, Any],
):
    """测试获取任务标签列表成功"""
    # 创建任务和标签
    task_response = await client.post(
        "/tasks", json=sample_task_data, headers=auth_headers
    )
    task_id = task_response.json()["id"]

    tag_response = await client.post(
        "/tags", json=sample_tag_data, headers=auth_headers
    )
    tag_id = tag_response.json()["id"]

    response = await client.get(f"/tasks/{task_id}/tags", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_add_task_tag_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_task_data: Dict[str, Any],
    sample_tag_data: Dict[str, Any],
):
    """测试为任务添加标签成功"""
    # 创建任务和标签
    task_response = await client.post(
        "/tasks", json=sample_task_data, headers=auth_headers
    )
    task_id = task_response.json()["id"]

    tag_response = await client.post(
        "/tags", json=sample_tag_data, headers=auth_headers
    )
    tag_id = tag_response.json()["id"]

    tag_data = {"tag_id": tag_id}
    response = await client.post(
        f"/tasks/{task_id}/tags", json=tag_data, headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert "task_id" in data
    assert "tag_id" in data


@pytest.mark.asyncio
async def test_remove_task_tag_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_task_data: Dict[str, Any],
    sample_tag_data: Dict[str, Any],
):
    """测试从任务移除标签成功"""
    # 创建任务和标签，并关联
    task_response = await client.post(
        "/tasks", json=sample_task_data, headers=auth_headers
    )
    task_id = task_response.json()["id"]

    tag_response = await client.post(
        "/tags", json=sample_tag_data, headers=auth_headers
    )
    tag_id = tag_response.json()["id"]

    await client.post(
        f"/tasks/{task_id}/tags", json={"tag_id": tag_id}, headers=auth_headers
    )

    response = await client.delete(
        f"/tasks/{task_id}/tags/{tag_id}", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data == {}


# ======================
# COMMENT ENDPOINT TESTS
# ======================


@pytest.mark.asyncio
async def test_get_task_comments_success(
    client: AsyncClient, auth_headers: Dict[str, str], sample_task_data: Dict[str, Any]
):
    """测试获取任务评论列表成功"""
    task_response = await client.post(
        "/tasks", json=sample_task_data, headers=auth_headers
    )
    task_id = task_response.json()["id"]

    response = await client.get(f"/tasks/{task_id}/comments", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_create_comment_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_task_data: Dict[str, Any],
    sample_comment_data: Dict[str, Any],
):
    """测试创建评论成功"""
    task_response = await client.post(
        "/tasks", json=sample_task_data, headers=auth_headers
    )
    task_id = task_response.json()["id"]

    response = await client.post(
        f"/tasks/{task_id}/comments", json=sample_comment_data, headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["content"] == sample_comment_data["content"]


@pytest.mark.asyncio
async def test_get_comment_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_task_data: Dict[str, Any],
    sample_comment_data: Dict[str, Any],
):
    """测试获取单条评论成功"""
    task_response = await client.post(
        "/tasks", json=sample_task_data, headers=auth_headers
    )
    task_id = task_response.json()["id"]

    comment_response = await client.post(
        f"/tasks/{task_id}/comments", json=sample_comment_data, headers=auth_headers
    )
    comment_id = comment_response.json()["id"]

    response = await client.get(f"/comments/{comment_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == comment_id


@pytest.mark.asyncio
async def test_update_comment_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_task_data: Dict[str, Any],
    sample_comment_data: Dict[str, Any],
):
    """测试更新评论成功"""
    task_response = await client.post(
        "/tasks", json=sample_task_data, headers=auth_headers
    )
    task_id = task_response.json()["id"]

    comment_response = await client.post(
        f"/tasks/{task_id}/comments", json=sample_comment_data, headers=auth_headers
    )
    comment_id = comment_response.json()["id"]

    update_data = {"content": "Updated comment content"}
    response = await client.put(
        f"/comments/{comment_id}", json=update_data, headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == update_data["content"]


@pytest.mark.asyncio
async def test_delete_comment_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_task_data: Dict[str, Any],
    sample_comment_data: Dict[str, Any],
):
    """测试删除评论成功"""
    task_response = await client.post(
        "/tasks", json=sample_task_data, headers=auth_headers
    )
    task_id = task_response.json()["id"]

    comment_response = await client.post(
        f"/tasks/{task_id}/comments", json=sample_comment_data, headers=auth_headers
    )
    comment_id = comment_response.json()["id"]

    response = await client.delete(f"/comments/{comment_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data == {}


# ======================
# ATTACHMENT ENDPOINT TESTS
# ======================


@pytest.mark.asyncio
async def test_get_task_attachments_success(
    client: AsyncClient, auth_headers: Dict[str, str], sample_task_data: Dict[str, Any]
):
    """测试获取任务附件列表成功"""
    task_response = await client.post(
        "/tasks", json=sample_task_data, headers=auth_headers
    )
    task_id = task_response.json()["id"]

    response = await client.get(f"/tasks/{task_id}/attachments", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_create_attachment_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_task_data: Dict[str, Any],
    sample_attachment_data: Dict[str, Any],
):
    """测试创建附件成功"""
    task_response = await client.post(
        "/tasks", json=sample_task_data, headers=auth_headers
    )
    task_id = task_response.json()["id"]

    response = await client.post(
        f"/tasks/{task_id}/attachments",
        json=sample_attachment_data,
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["filename"] == sample_attachment_data["filename"]


@pytest.mark.asyncio
async def test_get_attachment_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_task_data: Dict[str, Any],
    sample_attachment_data: Dict[str, Any],
):
    """测试获取单个附件成功"""
    task_response = await client.post(
        "/tasks", json=sample_task_data, headers=auth_headers
    )
    task_id = task_response.json()["id"]

    attachment_response = await client.post(
        f"/tasks/{task_id}/attachments",
        json=sample_attachment_data,
        headers=auth_headers,
    )
    attachment_id = attachment_response.json()["id"]

    response = await client.get(f"/attachments/{attachment_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == attachment_id


@pytest.mark.asyncio
async def test_delete_attachment_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_task_data: Dict[str, Any],
    sample_attachment_data: Dict[str, Any],
):
    """测试删除附件成功"""
    task_response = await client.post(
        "/tasks", json=sample_task_data, headers=auth_headers
    )
    task_id = task_response.json()["id"]

    attachment_response = await client.post(
        f"/tasks/{task_id}/attachments",
        json=sample_attachment_data,
        headers=auth_headers,
    )
    attachment_id = attachment_response.json()["id"]

    response = await client.delete(
        f"/attachments/{attachment_id}", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data == {}


# ======================
# BOUNDARY CONDITION TESTS
# ======================


@pytest.mark.asyncio
async def test_get_projects_boundary_pagination(
    client: AsyncClient, auth_headers: Dict[str, str]
):
    """测试项目列表分页边界条件"""
    # 测试 page=0
    response = await client.get(
        "/projects", params={"page": 0, "size": 10}, headers=auth_headers
    )
    assert response.status_code in [
        200,
        422,
    ]  # 可能返回200（如果后端处理）或422（如果验证失败）

    # 测试 size 超出范围
    response = await client.get(
        "/projects", params={"page": 1, "size": 1000}, headers=auth_headers
    )
    # 根据实际实现，可能返回200或422


@pytest.mark.asyncio
async def test_create_project_boundary_name_length(
    client: AsyncClient, auth_headers: Dict[str, str]
):
    """测试项目名称长度边界条件"""
    # 测试超长名称
    long_name = "A" * 256
    response = await client.post(
        "/projects",
        json={"name": long_name, "status": ProjectStatusEnum.ACTIVE.value},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_path_params(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试无效路径参数"""
    # 测试非数字ID
    response = await client.get("/projects/abc", headers=auth_headers)
    assert response.status_code == 422

    # 测试负数ID
    response = await client.get("/projects/-1", headers=auth_headers)
    assert response.status_code == 422
