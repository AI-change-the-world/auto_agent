import pytest
from httpx import AsyncClient
from typing import Dict, Any

# 假设这些模型类已定义在 schemas 模块中
from schemas import (
    CreateUserRequest,
    UpdateUserRequest,
    UserResponse,
    UserListResponse,
    CreateProjectRequest,
    UpdateProjectRequest,
    ProjectResponse,
    ProjectListResponse,
    EmptyResponse
)

# 假设 app 是 FastAPI 应用实例
from main import app


@pytest.fixture
async def client() -> AsyncClient:
    """提供测试客户端"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def valid_user_data() -> Dict[str, Any]:
    """有效的用户创建数据"""
    return {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User"
    }


@pytest.fixture
def valid_project_data() -> Dict[str, Any]:
    """有效的项目创建数据"""
    return {
        "name": "Test Project",
        "description": "A test project"
    }


@pytest.fixture
async def auth_headers(client: AsyncClient, valid_user_data: Dict[str, Any]) -> Dict[str, str]:
    """创建用户并返回认证头（假设通过某种方式获取 token）"""
    # 注意：实际实现可能需要根据认证机制调整
    # 这里简化处理，假设 POST /users 不需要认证且能直接使用
    response = await client.post("/users", json=valid_user_data)
    assert response.status_code == 201
    user = response.json()
    
    # 假设系统返回 token 或使用其他认证方式
    # 此处仅为示例，实际应根据真实认证逻辑实现
    return {"Authorization": f"Bearer fake-token-for-{user['id']}"}


@pytest.mark.asyncio
async def test_get_users_success(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试成功获取用户列表"""
    response = await client.get("/users", headers=auth_headers, params={"page": 1, "size": 10})
    assert response.status_code == 200
    data = response.json()
    # 验证响应结构
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "size" in data


@pytest.mark.asyncio
async def test_get_users_unauthorized(client: AsyncClient):
    """测试未认证时获取用户列表失败"""
    response = await client.get("/users")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_users_invalid_params(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试无效分页参数"""
    response = await client.get("/users", headers=auth_headers, params={"page": -1, "size": 0})
    # 根据实际验证逻辑，可能是422或400
    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_post_users_success(client: AsyncClient, valid_user_data: Dict[str, Any]):
    """测试成功创建用户"""
    response = await client.post("/users", json=valid_user_data)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["username"] == valid_user_data["username"]
    assert data["email"] == valid_user_data["email"]


@pytest.mark.asyncio
async def test_post_users_invalid_data(client: AsyncClient):
    """测试创建用户时提供无效数据"""
    invalid_data = {"username": "", "email": "invalid-email"}
    response = await client.post("/users", json=invalid_data)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_user_by_id_success(client: AsyncClient, auth_headers: Dict[str, str], valid_user_data: Dict[str, Any]):
    """测试成功获取单个用户"""
    # 先创建用户
    create_response = await client.post("/users", json=valid_user_data)
    assert create_response.status_code == 201
    user_id = create_response.json()["id"]
    
    response = await client.get(f"/users/{user_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user_id
    assert data["username"] == valid_user_data["username"]


@pytest.mark.asyncio
async def test_get_user_by_id_not_found(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试获取不存在的用户"""
    response = await client.get("/users/999999", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_user_by_id_unauthorized(client: AsyncClient, valid_user_data: Dict[str, Any]):
    """测试未认证时获取用户信息失败"""
    # 先创建用户
    create_response = await client.post("/users", json=valid_user_data)
    assert create_response.status_code == 201
    user_id = create_response.json()["id"]
    
    response = await client.get(f"/users/{user_id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_put_user_success(client: AsyncClient, auth_headers: Dict[str, str], valid_user_data: Dict[str, Any]):
    """测试成功更新用户"""
    # 先创建用户
    create_response = await client.post("/users", json=valid_user_data)
    assert create_response.status_code == 201
    user_id = create_response.json()["id"]
    
    update_data = {"full_name": "Updated Name"}
    response = await client.put(f"/users/{user_id}", json=update_data, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Updated Name"


@pytest.mark.asyncio
async def test_put_user_not_found(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试更新不存在的用户"""
    update_data = {"full_name": "Updated Name"}
    response = await client.put("/users/999999", json=update_data, headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_user_success(client: AsyncClient, auth_headers: Dict[str, str], valid_user_data: Dict[str, Any]):
    """测试成功删除用户"""
    # 先创建用户
    create_response = await client.post("/users", json=valid_user_data)
    assert create_response.status_code == 201
    user_id = create_response.json()["id"]
    
    response = await client.delete(f"/users/{user_id}", headers=auth_headers)
    assert response.status_code == 200
    # 验证是否为空响应
    assert response.json() == {}


@pytest.mark.asyncio
async def test_delete_user_not_found(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试删除不存在的用户"""
    response = await client.delete("/users/999999", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_user_projects_success(client: AsyncClient, auth_headers: Dict[str, str], valid_user_data: Dict[str, Any]):
    """测试成功获取用户项目列表"""
    # 先创建用户
    create_user_response = await client.post("/users", json=valid_user_data)
    assert create_user_response.status_code == 201
    user_id = create_user_response.json()["id"]
    
    response = await client.get(f"/users/{user_id}/projects", headers=auth_headers, params={"page": 1, "size": 10})
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_get_user_projects_unauthorized(client: AsyncClient, valid_user_data: Dict[str, Any]):
    """测试未认证时获取用户项目列表失败"""
    # 先创建用户
    create_user_response = await client.post("/users", json=valid_user_data)
    assert create_user_response.status_code == 201
    user_id = create_user_response.json()["id"]
    
    response = await client.get(f"/users/{user_id}/projects")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_projects_success(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试成功获取项目列表"""
    response = await client.get("/projects", headers=auth_headers, params={"page": 1, "size": 10})
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_get_projects_unauthorized(client: AsyncClient):
    """测试未认证时获取项目列表失败"""
    response = await client.get("/projects")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_post_projects_success(client: AsyncClient, auth_headers: Dict[str, str], valid_project_data: Dict[str, Any]):
    """测试成功创建项目"""
    response = await client.post("/projects", json=valid_project_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["name"] == valid_project_data["name"]


@pytest.mark.asyncio
async def test_post_projects_unauthorized(client: AsyncClient, valid_project_data: Dict[str, Any]):
    """测试未认证时创建项目失败"""
    response = await client.post("/projects", json=valid_project_data)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_post_projects_invalid_data(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试创建项目时提供无效数据"""
    invalid_data = {"name": ""}
    response = await client.post("/projects", json=invalid_data, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_project_by_id_success(client: AsyncClient, auth_headers: Dict[str, str], valid_project_data: Dict[str, Any]):
    """测试成功获取单个项目"""
    # 先创建项目
    create_response = await client.post("/projects", json=valid_project_data, headers=auth_headers)
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]
    
    response = await client.get(f"/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == project_id
    assert data["name"] == valid_project_data["name"]


@pytest.mark.asyncio
async def test_get_project_by_id_not_found(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试获取不存在的项目"""
    response = await client.get("/projects/999999", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_put_project_success(client: AsyncClient, auth_headers: Dict[str, str], valid_project_data: Dict[str, Any]):
    """测试成功更新项目"""
    # 先创建项目
    create_response = await client.post("/projects", json=valid_project_data, headers=auth_headers)
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]
    
    update_data = {"description": "Updated description"}
    response = await client.put(f"/projects/{project_id}", json=update_data, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == "Updated description"


@pytest.mark.asyncio
async def test_put_project_not_found(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试更新不存在的项目"""
    update_data = {"description": "Updated description"}
    response = await client.put("/projects/999999", json=update_data, headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_project_success(client: AsyncClient, auth_headers: Dict[str, str], valid_project_data: Dict[str, Any]):
    """测试成功删除项目"""
    # 先创建项目
    create_response = await client.post("/projects", json=valid_project_data, headers=auth_headers)
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]
    
    response = await client.delete(f"/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {}


@pytest.mark.asyncio
async def test_delete_project_not_found(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试删除不存在的项目"""
    response = await client.delete("/projects/999999", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_pagination_boundary_conditions(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试分页边界条件"""
    # 测试 page=0
    response = await client.get("/users", headers=auth_headers, params={"page": 0, "size": 10})
    assert response.status_code in (400, 422)
    
    # 测试 size 超出范围
    response = await client.get("/users", headers=auth_headers, params={"page": 1, "size": 1000})
    # 假设最大 size 为 100
    assert response.status_code in (400, 422)
    
    # 测试负数 size
    response = await client.get("/users", headers=auth_headers, params={"page": 1, "size": -5})
    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_path_param_validation(client: AsyncClient, auth_headers: Dict[str, str]):
    """测试路径参数验证"""
    # 测试非整数 ID
    response = await client.get("/users/abc", headers=auth_headers)
    assert response.status_code == 422
    
    # 测试负数 ID
    response = await client.get("/users/-1", headers=auth_headers)
    assert response.status_code == 422