import pytest
from httpx import AsyncClient, ASGITransport
from typing import Dict, Any, List
from datetime import datetime

# 假设你的 FastAPI 应用实例名为 app，位于 main.py 中
# from main import app

# 为演示目的，这里模拟一个简单的 app（实际使用时请替换为真实应用）
class MockApp:
    def __init__(self):
        pass

app = MockApp()


# ------------------ Fixtures ------------------

@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
async def client() -> AsyncClient:
    """提供测试用的异步 HTTP 客户端"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_project_data() -> Dict[str, Any]:
    return {
        "name": "Test Project",
        "description": "A test project",
        "status": "active"
    }


@pytest.fixture
def sample_user_data() -> Dict[str, Any]:
    return {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User"
    }


@pytest.fixture
def sample_task_data() -> Dict[str, Any]:
    return {
        "title": "Test Task",
        "description": "A test task",
        "priority": "medium",
        "status": "todo"
    }


@pytest.fixture
def sample_tag_data() -> Dict[str, Any]:
    return {
        "name": "Urgent",
        "color": "#FF0000"
    }


# ------------------ Helper Functions ------------------

async def create_project(client: AsyncClient, data: Dict[str, Any]) -> Dict[str, Any]:
    response = await client.post("/projects", json=data)
    assert response.status_code == 201
    return response.json()


async def create_user(client: AsyncClient, data: Dict[str, Any]) -> Dict[str, Any]:
    response = await client.post("/users", json=data)  # 假设有此端点，否则需调整
    assert response.status_code == 201
    return response.json()


async def create_task(client: AsyncClient, project_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    response = await client.post(f"/projects/{project_id}/tasks", json=data)
    assert response.status_code == 201
    return response.json()


async def create_tag(client: AsyncClient, data: Dict[str, Any]) -> Dict[str, Any]:
    response = await client.post("/tags", json=data)
    assert response.status_code == 201
    return response.json()


# ------------------ Project Tests ------------------

@pytest.mark.asyncio
async def test_get_projects_empty(client: AsyncClient):
    response = await client.get("/projects")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_and_get_project(client: AsyncClient, sample_project_data: Dict[str, Any]):
    # 创建项目
    create_resp = await client.post("/projects", json=sample_project_data)
    assert create_resp.status_code == 201
    project = create_resp.json()
    assert project["name"] == sample_project_data["name"]
    assert "id" in project

    # 获取项目列表
    list_resp = await client.get("/projects")
    assert list_resp.status_code == 200
    projects = list_resp.json()
    assert len(projects) == 1
    assert projects[0]["id"] == project["id"]

    # 获取单个项目
    get_resp = await client.get(f"/projects/{project['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == project["id"]


@pytest.mark.asyncio
async def test_update_project(client: AsyncClient, sample_project_data: Dict[str, Any]):
    project = await create_project(client, sample_project_data)
    update_data = {"name": "Updated Project", "description": "Updated description"}
    response = await client.put(f"/projects/{project['id']}", json=update_data)
    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == update_data["name"]
    assert updated["description"] == update_data["description"]


@pytest.mark.asyncio
async def test_delete_project(client: AsyncClient, sample_project_data: Dict[str, Any]):
    project = await create_project(client, sample_project_data)
    delete_resp = await client.delete(f"/projects/{project['id']}")
    assert delete_resp.status_code == 204

    get_resp = await client.get(f"/projects/{project['id']}")
    assert get_resp.status_code == 404


# ------------------ Task Tests ------------------

@pytest.mark.asyncio
async def test_create_and_get_tasks(client: AsyncClient, sample_project_data: Dict[str, Any], sample_task_data: Dict[str, Any]):
    project = await create_project(client, sample_project_data)
    task = await create_task(client, project["id"], sample_task_data)

    # 获取项目下的任务
    response = await client.get(f"/projects/{project['id']}/tasks")
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 1
    assert tasks[0]["id"] == task["id"]

    # 获取单个任务
    task_resp = await client.get(f"/tasks/{task['id']}")
    assert task_resp.status_code == 200
    assert task_resp.json()["id"] == task["id"]


@pytest.mark.asyncio
async def test_update_task(client: AsyncClient, sample_project_data: Dict[str, Any], sample_task_data: Dict[str, Any]):
    project = await create_project(client, sample_project_data)
    task = await create_task(client, project["id"], sample_task_data)
    update_data = {"title": "Updated Task", "status": "in_progress"}
    response = await client.put(f"/tasks/{task['id']}", json=update_data)
    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == update_data["title"]
    assert updated["status"] == update_data["status"]


@pytest.mark.asyncio
async def test_delete_task(client: AsyncClient, sample_project_data: Dict[str, Any], sample_task_data: Dict[str, Any]):
    project = await create_project(client, sample_project_data)
    task = await create_task(client, project["id"], sample_task_data)
    delete_resp = await client.delete(f"/tasks/{task['id']}")
    assert delete_resp.status_code == 204

    get_resp = await client.get(f"/tasks/{task['id']}")
    assert get_resp.status_code == 404


# ------------------ Tag Tests ------------------

@pytest.mark.asyncio
async def test_create_and_get_tags(client: AsyncClient, sample_tag_data: Dict[str, Any]):
    tag = await create_tag(client, sample_tag_data)

    # 获取所有标签
    list_resp = await client.get("/tags")
    assert list_resp.status_code == 200
    tags = list_resp.json()
    assert len(tags) == 1
    assert tags[0]["id"] == tag["id"]

    # 获取单个标签
    get_resp = await client.get(f"/tags/{tag['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == tag["id"]


@pytest.mark.asyncio
async def test_update_tag(client: AsyncClient, sample_tag_data: Dict[str, Any]):
    tag = await create_tag(client, sample_tag_data)
    update_data = {"name": "Critical", "color": "#0000FF"}
    response = await client.put(f"/tags/{tag['id']}", json=update_data)
    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == update_data["name"]
    assert updated["color"] == update_data["color"]


@pytest.mark.asyncio
async def test_delete_tag(client: AsyncClient, sample_tag_data: Dict[str, Any]):
    tag = await create_tag(client, sample_tag_data)
    delete_resp = await client.delete(f"/tags/{tag['id']}")
    assert delete_resp.status_code == 204

    get_resp = await client.get(f"/tags/{tag['id']}")
    assert get_resp.status_code == 404


# ------------------ Task-Tag Association Tests ------------------

@pytest.mark.asyncio
async def test_add_and_remove_tag_from_task(
    client: AsyncClient,
    sample_project_data: Dict[str, Any],
    sample_task_data: Dict[str, Any],
    sample_tag_data: Dict[str, Any]
):
    project = await create_project(client, sample_project_data)
    task = await create_task(client, project["id"], sample_task_data)
    tag = await create_tag(client, sample_tag_data)

    # 为任务添加标签
    add_resp = await client.post(f"/tasks/{task['id']}/tags", json={"tag_id": tag["id"]})
    assert add_resp.status_code == 201

    # 获取任务的标签
    get_tags_resp = await client.get(f"/tasks/{task['id']}/tags")
    assert get_tags_resp.status_code == 200
    tags = get_tags_resp.json()
    assert len(tags) == 1
    assert tags[0]["id"] == tag["id"]

    # 移除标签
    remove_resp = await client.delete(f"/tasks/{task['id']}/tags/{tag['id']}")
    assert remove_resp.status_code == 204

    # 再次获取应为空
    get_tags_resp2 = await client.get(f"/tasks/{task['id']}/tags")
    assert get_tags_resp2.status_code == 200
    assert get_tags_resp2.json() == []


# ------------------ Project Member Tests ------------------

@pytest.mark.asyncio
async def test_add_and_remove_member_from_project(
    client: AsyncClient,
    sample_project_data: Dict[str, Any],
    sample_user_data: Dict[str, Any]
):
    project = await create_project(client, sample_project_data)

    # 假设用户已存在或通过其他方式创建（此处简化：直接 POST 到 members）
    # 注意：实际中可能需要先创建用户，但根据提供的端点，/users 只有 GET 和 GET/{id}
    # 因此我们假设用户 ID 是已知的（例如 1）

    user_id = 1

    # 添加成员
    add_resp = await client.post(f"/projects/{project['id']}/members", json={"user_id": user_id})
    assert add_resp.status_code == 201

    # 获取成员列表
    members_resp = await client.get(f"/projects/{project['id']}/members")
    assert members_resp.status_code == 200
    members = members_resp.json()
    assert len(members) == 1
    assert members[0]["user_id"] == user_id

    # 移除成员
    remove_resp = await client.delete(f"/projects/{project['id']}/members/{user_id}")
    assert remove_resp.status_code == 204

    # 再次获取应为空
    members_resp2 = await client.get(f"/projects/{project['id']}/members")
    assert members_resp2.status_code == 200
    assert members_resp2.json() == []


# ------------------ User Tests ------------------

@pytest.mark.asyncio
async def test_get_users_and_user(client: AsyncClient):
    # 假设系统中已有用户（例如 ID=1）
    user_id = 1

    # 获取用户列表
    users_resp = await client.get("/users")
    assert users_resp.status_code == 200
    assert isinstance(users_resp.json(), list)

    # 获取特定用户
    user_resp = await client.get(f"/users/{user_id}")
    # 如果用户存在，状态码应为 200；若不存在则为 404
    # 此处仅验证响应结构合理
    assert user_resp.status_code in (200, 404)


# ------------------ Exception Tests ------------------

@pytest.mark.asyncio
async def test_get_nonexistent_project(client: AsyncClient):
    response = await client.get("/projects/999999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_nonexistent_project(client: AsyncClient):
    response = await client.put("/projects/999999", json={"name": "Fake"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_project(client: AsyncClient):
    response = await client.delete("/projects/999999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_project_invalid_data(client: AsyncClient):
    invalid_data = {"name": ""}  # 假设 name 不能为空
    response = await client.post("/projects", json=invalid_data)
    assert response.status_code == 422  # Pydantic 验证错误


@pytest.mark.asyncio
async def test_add_member_to_nonexistent_project(client: AsyncClient):
    response = await client.post("/projects/999999/members", json={"user_id": 1})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_remove_member_from_nonexistent_project(client: AsyncClient):
    response = await client.delete("/projects/999999/members/1")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_tasks_for_nonexistent_project(client: AsyncClient):
    response = await client.get("/projects/999999/tasks")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_task_in_nonexistent_project(client: AsyncClient, sample_task_data: Dict[str, Any]):
    response = await client.post("/projects/999999/tasks", json=sample_task_data)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_add_tag_to_nonexistent_task(client: AsyncClient):
    response = await client.post("/tasks/999999/tags", json={"tag_id": 1})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_remove_tag_from_nonexistent_task(client: AsyncClient):
    response = await client.delete("/tasks/999999/tags/1")
    assert response.status_code == 404