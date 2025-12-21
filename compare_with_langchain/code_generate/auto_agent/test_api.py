from enum import Enum
from typing import Any, Dict, List

import pytest
from httpx import AsyncClient

# 假设应用实例
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
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    # 假设使用 Bearer Token 认证
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def sample_project_data() -> Dict[str, Any]:
    return {
        "name": "Test Project",
        "description": "A test project for integration testing",
        "status": ProjectStatusEnum.ACTIVE.value,
    }


@pytest.fixture
def sample_task_data() -> Dict[str, Any]:
    return {
        "title": "Test Task",
        "description": "A test task",
        "status": TaskStatusEnum.TODO.value,
        "priority": TaskPriorityEnum.MEDIUM.value,
        "assignee_id": 1,
    }


@pytest.fixture
def sample_tag_data() -> Dict[str, Any]:
    return {"name": "Urgent", "color": "#FF0000"}


@pytest.fixture
def sample_comment_data() -> Dict[str, Any]:
    return {"content": "This is a test comment"}


@pytest.fixture
def sample_attachment_data() -> Dict[str, Any]:
    return {"filename": "test.txt", "content_type": "text/plain"}


# ======================
# Project Endpoints Tests
# ======================


@pytest.mark.asyncio
async def test_get_projects_success(client: AsyncClient, auth_headers: Dict[str, str]):
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
    params = {"page": 1, "size": 10, "status": ProjectStatusEnum.ACTIVE.value}
    response = await client.get("/projects", params=params, headers=auth_headers)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_create_project_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
):
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
    invalid_data = {"name": ""}  # name is required and non-empty
    response = await client.post("/projects", json=invalid_data, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_project_success(client: AsyncClient, auth_headers: Dict[str, str]):
    # First create a project
    project_data = {
        "name": "Test Get Project",
        "status": ProjectStatusEnum.ACTIVE.value,
    }
    create_response = await client.post(
        "/projects", json=project_data, headers=auth_headers
    )
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]

    # Then get it
    response = await client.get(f"/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == project_id
    assert data["name"] == project_data["name"]


@pytest.mark.asyncio
async def test_get_project_not_found(client: AsyncClient, auth_headers: Dict[str, str]):
    response = await client.get("/projects/999999", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_project_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
):
    # Create project first
    create_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]

    # Update project
    update_data = {"name": "Updated Project Name", "description": "Updated description"}
    response = await client.put(
        f"/projects/{project_id}", json=update_data, headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == update_data["name"]
    assert data["description"] == update_data["description"]


@pytest.mark.asyncio
async def test_update_project_not_found(
    client: AsyncClient, auth_headers: Dict[str, str]
):
    update_data = {"name": "Non-existent Project"}
    response = await client.put(
        "/projects/999999", json=update_data, headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_project_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
):
    # Create project first
    create_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]

    # Delete project
    response = await client.delete(f"/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    # EmptyResponse should be empty or have success field
    assert isinstance(data, dict)


@pytest.mark.asyncio
async def test_delete_project_not_found(
    client: AsyncClient, auth_headers: Dict[str, str]
):
    response = await client.delete("/projects/999999", headers=auth_headers)
    assert response.status_code == 404


# ======================
# Project Members Endpoints Tests
# ======================


@pytest.mark.asyncio
async def test_get_project_members_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
):
    # Create project first
    create_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_response.status_code == 201
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
    # Create project first
    create_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]

    member_data = {"user_id": 2, "role": "member"}
    response = await client.post(
        f"/projects/{project_id}/members", json=member_data, headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == member_data["user_id"]


@pytest.mark.asyncio
async def test_remove_project_member_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
):
    # Create project first
    create_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]

    # Add member first
    member_data = {"user_id": 3, "role": "member"}
    add_response = await client.post(
        f"/projects/{project_id}/members", json=member_data, headers=auth_headers
    )
    assert add_response.status_code == 201

    # Remove member
    response = await client.delete(
        f"/projects/{project_id}/members/3", headers=auth_headers
    )
    assert response.status_code == 200


# ======================
# User Endpoints Tests
# ======================


@pytest.mark.asyncio
async def test_get_users_success(client: AsyncClient, auth_headers: Dict[str, str]):
    response = await client.get("/users", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_get_user_success(client: AsyncClient, auth_headers: Dict[str, str]):
    # Assuming user with ID 1 exists
    response = await client.get("/users/1", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["id"] == 1


@pytest.mark.asyncio
async def test_get_user_not_found(client: AsyncClient, auth_headers: Dict[str, str]):
    response = await client.get("/users/999999", headers=auth_headers)
    assert response.status_code == 404


# ======================
# Task Endpoints Tests
# ======================


@pytest.mark.asyncio
async def test_get_project_tasks_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
):
    # Create project first
    create_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]

    response = await client.get(f"/projects/{project_id}/tasks", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_create_task_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_task_data: Dict[str, Any],
):
    # Create project first
    create_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]

    response = await client.post(
        f"/projects/{project_id}/tasks", json=sample_task_data, headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == sample_task_data["title"]
    assert data["project_id"] == project_id


@pytest.mark.asyncio
async def test_get_task_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_task_data: Dict[str, Any],
):
    # Create project and task
    create_proj_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_proj_response.status_code == 201
    project_id = create_proj_response.json()["id"]

    create_task_response = await client.post(
        f"/projects/{project_id}/tasks", json=sample_task_data, headers=auth_headers
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    response = await client.get(f"/tasks/{task_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == task_id


@pytest.mark.asyncio
async def test_update_task_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_task_data: Dict[str, Any],
):
    # Create project and task
    create_proj_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_proj_response.status_code == 201
    project_id = create_proj_response.json()["id"]

    create_task_response = await client.post(
        f"/projects/{project_id}/tasks", json=sample_task_data, headers=auth_headers
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    update_data = {
        "title": "Updated Task Title",
        "status": TaskStatusEnum.IN_PROGRESS.value,
    }
    response = await client.put(
        f"/tasks/{task_id}", json=update_data, headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == update_data["title"]


@pytest.mark.asyncio
async def test_delete_task_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_task_data: Dict[str, Any],
):
    # Create project and task
    create_proj_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_proj_response.status_code == 201
    project_id = create_proj_response.json()["id"]

    create_task_response = await client.post(
        f"/projects/{project_id}/tasks", json=sample_task_data, headers=auth_headers
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    response = await client.delete(f"/tasks/{task_id}", headers=auth_headers)
    assert response.status_code == 200


# ======================
# Subtask Endpoints Tests
# ======================


@pytest.mark.asyncio
async def test_get_task_subtasks_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_task_data: Dict[str, Any],
):
    # Create project and parent task
    create_proj_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_proj_response.status_code == 201
    project_id = create_proj_response.json()["id"]

    create_parent_task_response = await client.post(
        f"/projects/{project_id}/tasks", json=sample_task_data, headers=auth_headers
    )
    assert create_parent_task_response.status_code == 201
    parent_task_id = create_parent_task_response.json()["id"]

    response = await client.get(
        f"/tasks/{parent_task_id}/subtasks", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


# ======================
# Tag Endpoints Tests
# ======================


@pytest.mark.asyncio
async def test_get_project_tags_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
):
    # Create project first
    create_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]

    response = await client.get(f"/projects/{project_id}/tags", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_create_tag_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_tag_data: Dict[str, Any],
):
    # Create project first
    create_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]

    response = await client.post(
        f"/projects/{project_id}/tags", json=sample_tag_data, headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == sample_tag_data["name"]


@pytest.mark.asyncio
async def test_get_tag_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_tag_data: Dict[str, Any],
):
    # Create project and tag
    create_proj_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_proj_response.status_code == 201
    project_id = create_proj_response.json()["id"]

    create_tag_response = await client.post(
        f"/projects/{project_id}/tags", json=sample_tag_data, headers=auth_headers
    )
    assert create_tag_response.status_code == 201
    tag_id = create_tag_response.json()["id"]

    response = await client.get(f"/tags/{tag_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == tag_id


@pytest.mark.asyncio
async def test_update_tag_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_tag_data: Dict[str, Any],
):
    # Create project and tag
    create_proj_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_proj_response.status_code == 201
    project_id = create_proj_response.json()["id"]

    create_tag_response = await client.post(
        f"/projects/{project_id}/tags", json=sample_tag_data, headers=auth_headers
    )
    assert create_tag_response.status_code == 201
    tag_id = create_tag_response.json()["id"]

    update_data = {"name": "Updated Tag", "color": "#00FF00"}
    response = await client.put(
        f"/tags/{tag_id}", json=update_data, headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == update_data["name"]


@pytest.mark.asyncio
async def test_delete_tag_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_tag_data: Dict[str, Any],
):
    # Create project and tag
    create_proj_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_proj_response.status_code == 201
    project_id = create_proj_response.json()["id"]

    create_tag_response = await client.post(
        f"/projects/{project_id}/tags", json=sample_tag_data, headers=auth_headers
    )
    assert create_tag_response.status_code == 201
    tag_id = create_tag_response.json()["id"]

    response = await client.delete(f"/tags/{tag_id}", headers=auth_headers)
    assert response.status_code == 200


# ======================
# Task-Tag Association Tests
# ======================


@pytest.mark.asyncio
async def test_add_tag_to_task_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_task_data: Dict[str, Any],
    sample_tag_data: Dict[str, Any],
):
    # Create project, task, and tag
    create_proj_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_proj_response.status_code == 201
    project_id = create_proj_response.json()["id"]

    create_task_response = await client.post(
        f"/projects/{project_id}/tasks", json=sample_task_data, headers=auth_headers
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    create_tag_response = await client.post(
        f"/projects/{project_id}/tags", json=sample_tag_data, headers=auth_headers
    )
    assert create_tag_response.status_code == 201
    tag_id = create_tag_response.json()["id"]

    association_data = {"tag_id": tag_id}
    response = await client.post(
        f"/tasks/{task_id}/tags", json=association_data, headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["task_id"] == task_id
    assert data["tag_id"] == tag_id


@pytest.mark.asyncio
async def test_remove_tag_from_task_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_task_data: Dict[str, Any],
    sample_tag_data: Dict[str, Any],
):
    # Create project, task, and tag
    create_proj_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_proj_response.status_code == 201
    project_id = create_proj_response.json()["id"]

    create_task_response = await client.post(
        f"/projects/{project_id}/tasks", json=sample_task_data, headers=auth_headers
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    create_tag_response = await client.post(
        f"/projects/{project_id}/tags", json=sample_tag_data, headers=auth_headers
    )
    assert create_tag_response.status_code == 201
    tag_id = create_tag_response.json()["id"]

    # Add tag to task first
    association_data = {"tag_id": tag_id}
    add_response = await client.post(
        f"/tasks/{task_id}/tags", json=association_data, headers=auth_headers
    )
    assert add_response.status_code == 201

    # Remove tag from task
    response = await client.delete(
        f"/tasks/{task_id}/tags/{tag_id}", headers=auth_headers
    )
    assert response.status_code == 200


# ======================
# Comment Endpoints Tests
# ======================


@pytest.mark.asyncio
async def test_get_task_comments_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_task_data: Dict[str, Any],
):
    # Create project and task
    create_proj_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_proj_response.status_code == 201
    project_id = create_proj_response.json()["id"]

    create_task_response = await client.post(
        f"/projects/{project_id}/tasks", json=sample_task_data, headers=auth_headers
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    response = await client.get(f"/tasks/{task_id}/comments", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_create_comment_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_task_data: Dict[str, Any],
    sample_comment_data: Dict[str, Any],
):
    # Create project and task
    create_proj_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_proj_response.status_code == 201
    project_id = create_proj_response.json()["id"]

    create_task_response = await client.post(
        f"/projects/{project_id}/tasks", json=sample_task_data, headers=auth_headers
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    response = await client.post(
        f"/tasks/{task_id}/comments", json=sample_comment_data, headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["content"] == sample_comment_data["content"]


@pytest.mark.asyncio
async def test_get_comment_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_task_data: Dict[str, Any],
    sample_comment_data: Dict[str, Any],
):
    # Create project, task, and comment
    create_proj_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_proj_response.status_code == 201
    project_id = create_proj_response.json()["id"]

    create_task_response = await client.post(
        f"/projects/{project_id}/tasks", json=sample_task_data, headers=auth_headers
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    create_comment_response = await client.post(
        f"/tasks/{task_id}/comments", json=sample_comment_data, headers=auth_headers
    )
    assert create_comment_response.status_code == 201
    comment_id = create_comment_response.json()["id"]

    response = await client.get(f"/comments/{comment_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == comment_id


@pytest.mark.asyncio
async def test_update_comment_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_task_data: Dict[str, Any],
    sample_comment_data: Dict[str, Any],
):
    # Create project, task, and comment
    create_proj_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_proj_response.status_code == 201
    project_id = create_proj_response.json()["id"]

    create_task_response = await client.post(
        f"/projects/{project_id}/tasks", json=sample_task_data, headers=auth_headers
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    create_comment_response = await client.post(
        f"/tasks/{task_id}/comments", json=sample_comment_data, headers=auth_headers
    )
    assert create_comment_response.status_code == 201
    comment_id = create_comment_response.json()["id"]

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
    sample_project_data: Dict[str, Any],
    sample_task_data: Dict[str, Any],
    sample_comment_data: Dict[str, Any],
):
    # Create project, task, and comment
    create_proj_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_proj_response.status_code == 201
    project_id = create_proj_response.json()["id"]

    create_task_response = await client.post(
        f"/projects/{project_id}/tasks", json=sample_task_data, headers=auth_headers
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    create_comment_response = await client.post(
        f"/tasks/{task_id}/comments", json=sample_comment_data, headers=auth_headers
    )
    assert create_comment_response.status_code == 201
    comment_id = create_comment_response.json()["id"]

    response = await client.delete(f"/comments/{comment_id}", headers=auth_headers)
    assert response.status_code == 200


# ======================
# Attachment Endpoints Tests
# ======================


@pytest.mark.asyncio
async def test_get_task_attachments_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_task_data: Dict[str, Any],
):
    # Create project and task
    create_proj_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_proj_response.status_code == 201
    project_id = create_proj_response.json()["id"]

    create_task_response = await client.post(
        f"/projects/{project_id}/tasks", json=sample_task_data, headers=auth_headers
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    response = await client.get(f"/tasks/{task_id}/attachments", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_create_attachment_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_task_data: Dict[str, Any],
    sample_attachment_data: Dict[str, Any],
):
    # Create project and task
    create_proj_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_proj_response.status_code == 201
    project_id = create_proj_response.json()["id"]

    create_task_response = await client.post(
        f"/projects/{project_id}/tasks", json=sample_task_data, headers=auth_headers
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    # For multipart upload, we'd typically send files, but for API testing with JSON,
    # we assume the endpoint accepts metadata via JSON
    response = await client.post(
        f"/tasks/{task_id}/attachments",
        json=sample_attachment_data,
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == sample_attachment_data["filename"]


@pytest.mark.asyncio
async def test_get_attachment_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_task_data: Dict[str, Any],
    sample_attachment_data: Dict[str, Any],
):
    # Create project, task, and attachment
    create_proj_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_proj_response.status_code == 201
    project_id = create_proj_response.json()["id"]

    create_task_response = await client.post(
        f"/projects/{project_id}/tasks", json=sample_task_data, headers=auth_headers
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    create_attachment_response = await client.post(
        f"/tasks/{task_id}/attachments",
        json=sample_attachment_data,
        headers=auth_headers,
    )
    assert create_attachment_response.status_code == 201
    attachment_id = create_attachment_response.json()["id"]

    response = await client.get(f"/attachments/{attachment_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == attachment_id


@pytest.mark.asyncio
async def test_delete_attachment_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_task_data: Dict[str, Any],
    sample_attachment_data: Dict[str, Any],
):
    # Create project, task, and attachment
    create_proj_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_proj_response.status_code == 201
    project_id = create_proj_response.json()["id"]

    create_task_response = await client.post(
        f"/projects/{project_id}/tasks", json=sample_task_data, headers=auth_headers
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    create_attachment_response = await client.post(
        f"/tasks/{task_id}/attachments",
        json=sample_attachment_data,
        headers=auth_headers,
    )
    assert create_attachment_response.status_code == 201
    attachment_id = create_attachment_response.json()["id"]

    response = await client.delete(
        f"/attachments/{attachment_id}", headers=auth_headers
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_download_attachment_success(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    sample_project_data: Dict[str, Any],
    sample_task_data: Dict[str, Any],
    sample_attachment_data: Dict[str, Any],
):
    # Create project, task, and attachment
    create_proj_response = await client.post(
        "/projects", json=sample_project_data, headers=auth_headers
    )
    assert create_proj_response.status_code == 201
    project_id = create_proj_response.json()["id"]

    create_task_response = await client.post(
        f"/projects/{project_id}/tasks", json=sample_task_data, headers=auth_headers
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    create_attachment_response = await client.post(
        f"/tasks/{task_id}/attachments",
        json=sample_attachment_data,
        headers=auth_headers,
    )
    assert create_attachment_response.status_code == 201
    attachment_id = create_attachment_response.json()["id"]

    response = await client.get(
        f"/attachments/{attachment_id}/download", headers=auth_headers
    )
    # For file download, status code should be 200 and content-type should be appropriate
    assert response.status_code == 200
    assert "content-type" in response.headers


# ======================
# Authentication Tests
# ======================


@pytest.mark.asyncio
async def test_unauthorized_access(client: AsyncClient):
    """Test that endpoints require authentication"""
    response = await client.get("/projects")
    assert response.status_code == 401  # Unauthorized


# ======================
# Edge Case Tests
# ======================


@pytest.mark.asyncio
async def test_get_projects_invalid_page_size(
    client: AsyncClient, auth_headers: Dict[str, str]
):
    params = {"page": -1, "size": -5}
    response = await client.get("/projects", params=params, headers=auth_headers)
    # Depending on validation, this might be 422 or handled gracefully
    assert response.status_code in [200, 422]


@pytest.mark.asyncio
async def test_create_project_missing_required_fields(
    client: AsyncClient, auth_headers: Dict[str, str]
):
    invalid_data = {}  # Missing required fields
    response = await client.post("/projects", json=invalid_data, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_task_with_nonexistent_project(
    client: AsyncClient, auth_headers: Dict[str, str], sample_task_data: Dict[str, Any]
):
    response = await client.post(
        "/projects/999999/tasks", json=sample_task_data, headers=auth_headers
    )
    assert response.status_code == 404
