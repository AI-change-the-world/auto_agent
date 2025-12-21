import pytest
from httpx import AsyncClient
from typing import Dict, Any, List
from enum import Enum

# Mock models - in real scenario these would be imported from your project
class ProjectStatusEnum(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"

class TaskStatusEnum(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"

class TaskPriorityEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

# Mock response models
class EmptyResponse:
    pass

# Fixtures
@pytest.fixture
def test_user_data() -> Dict[str, Any]:
    return {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User"
    }

@pytest.fixture
def test_project_data() -> Dict[str, Any]:
    return {
        "name": "Test Project",
        "description": "A test project",
        "status": ProjectStatusEnum.ACTIVE.value
    }

@pytest.fixture
def test_task_data() -> Dict[str, Any]:
    return {
        "title": "Test Task",
        "description": "A test task",
        "status": TaskStatusEnum.TODO.value,
        "priority": TaskPriorityEnum.MEDIUM.value
    }

@pytest.fixture
def test_tag_data() -> Dict[str, Any]:
    return {
        "name": "Test Tag",
        "color": "#FF0000"
    }

@pytest.fixture
def test_comment_data() -> Dict[str, Any]:
    return {
        "content": "This is a test comment"
    }

@pytest.fixture
def test_attachment_data() -> Dict[str, Any]:
    return {
        "filename": "test.txt",
        "file_url": "http://example.com/test.txt",
        "size": 1024
    }

@pytest.fixture
async def client() -> AsyncClient:
    # In a real application, this would be your FastAPI app instance
    # For this example, we'll assume the base URL is configured properly
    async with AsyncClient(base_url="http://test") as ac:
        yield ac

@pytest.fixture
async def auth_headers() -> Dict[str, str]:
    # In a real application, this would contain actual authentication tokens
    return {"Authorization": "Bearer test-token"}

@pytest.fixture
async def created_user(client: AsyncClient, auth_headers: Dict[str, str], test_user_data: Dict[str, Any]) -> Dict[str, Any]:
    response = await client.post("/users", json=test_user_data, headers=auth_headers)
    assert response.status_code == 201
    return response.json()

@pytest.fixture
async def created_project(client: AsyncClient, auth_headers: Dict[str, str], test_project_data: Dict[str, Any]) -> Dict[str, Any]:
    response = await client.post("/projects", json=test_project_data, headers=auth_headers)
    assert response.status_code == 201
    return response.json()

@pytest.fixture
async def created_task(client: AsyncClient, auth_headers: Dict[str, str], created_project: Dict[str, Any], test_task_data: Dict[str, Any]) -> Dict[str, Any]:
    task_data = test_task_data.copy()
    task_data["project_id"] = created_project["id"]
    response = await client.post("/tasks", json=task_data, headers=auth_headers)
    assert response.status_code == 201
    return response.json()

@pytest.fixture
async def created_tag(client: AsyncClient, auth_headers: Dict[str, str], test_tag_data: Dict[str, Any]) -> Dict[str, Any]:
    response = await client.post("/tags", json=test_tag_data, headers=auth_headers)
    assert response.status_code == 201
    return response.json()

# Project endpoints tests
@pytest.mark.asyncio
async def test_get_projects_success(client: AsyncClient, auth_headers: Dict[str, str]):
    response = await client.get("/projects", headers=auth_headers)
    assert response.status_code == 200
    assert "items" in response.json()
    assert "total" in response.json()
    assert "page" in response.json()
    assert "size" in response.json()

@pytest.mark.asyncio
async def test_get_projects_with_pagination(client: AsyncClient, auth_headers: Dict[str, str]):
    response = await client.get("/projects?page=1&size=10", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["size"] == 10

@pytest.mark.asyncio
async def test_get_projects_with_status_filter(client: AsyncClient, auth_headers: Dict[str, str]):
    response = await client.get(f"/projects?status={ProjectStatusEnum.ACTIVE.value}", headers=auth_headers)
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_create_project_success(client: AsyncClient, auth_headers: Dict[str, str], test_project_data: Dict[str, Any]):
    response = await client.post("/projects", json=test_project_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == test_project_data["name"]
    assert data["description"] == test_project_data["description"]
    assert "id" in data

@pytest.mark.asyncio
async def test_create_project_validation_error(client: AsyncClient, auth_headers: Dict[str, str]):
    invalid_data = {"name": ""}  # Missing required fields
    response = await client.post("/projects", json=invalid_data, headers=auth_headers)
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_get_project_by_id_success(client: AsyncClient, auth_headers: Dict[str, str], created_project: Dict[str, Any]):
    project_id = created_project["id"]
    response = await client.get(f"/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == project_id
    assert data["name"] == created_project["name"]

@pytest.mark.asyncio
async def test_get_project_by_id_not_found(client: AsyncClient, auth_headers: Dict[str, str]):
    response = await client.get("/projects/999999", headers=auth_headers)
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_update_project_success(client: AsyncClient, auth_headers: Dict[str, str], created_project: Dict[str, Any]):
    project_id = created_project["id"]
    update_data = {"name": "Updated Project Name"}
    response = await client.put(f"/projects/{project_id}", json=update_data, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Project Name"
    assert data["id"] == project_id

@pytest.mark.asyncio
async def test_update_project_not_found(client: AsyncClient, auth_headers: Dict[str, str]):
    update_data = {"name": "Updated Project Name"}
    response = await client.put("/projects/999999", json=update_data, headers=auth_headers)
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_delete_project_success(client: AsyncClient, auth_headers: Dict[str, str], created_project: Dict[str, Any]):
    project_id = created_project["id"]
    response = await client.delete(f"/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 200
    # Verify deletion
    get_response = await client.get(f"/projects/{project_id}", headers=auth_headers)
    assert get_response.status_code == 404

@pytest.mark.asyncio
async def test_delete_project_not_found(client: AsyncClient, auth_headers: Dict[str, str]):
    response = await client.delete("/projects/999999", headers=auth_headers)
    assert response.status_code == 404

# Project members endpoints tests
@pytest.mark.asyncio
async def test_get_project_members_success(client: AsyncClient, auth_headers: Dict[str, str], created_project: Dict[str, Any], created_user: Dict[str, Any]):
    project_id = created_project["id"]
    # Add user to project first
    member_data = {"user_id": created_user["id"]}
    await client.post(f"/projects/{project_id}/members", json=member_data, headers=auth_headers)
    
    response = await client.get(f"/projects/{project_id}/members", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) > 0

@pytest.mark.asyncio
async def test_add_project_member_success(client: AsyncClient, auth_headers: Dict[str, str], created_project: Dict[str, Any], created_user: Dict[str, Any]):
    project_id = created_project["id"]
    member_data = {"user_id": created_user["id"]}
    response = await client.post(f"/projects/{project_id}/members", json=member_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == created_user["id"]
    assert data["project_id"] == project_id

@pytest.mark.asyncio
async def test_remove_project_member_success(client: AsyncClient, auth_headers: Dict[str, str], created_project: Dict[str, Any], created_user: Dict[str, Any]):
    project_id = created_project["id"]
    user_id = created_user["id"]
    # Add user to project first
    member_data = {"user_id": user_id}
    await client.post(f"/projects/{project_id}/members", json=member_data, headers=auth_headers)
    
    response = await client.delete(f"/projects/{project_id}/members/{user_id}", headers=auth_headers)
    assert response.status_code == 200
    
    # Verify removal
    members_response = await client.get(f"/projects/{project_id}/members", headers=auth_headers)
    members = members_response.json()["items"]
    assert not any(member["user_id"] == user_id for member in members)

# User endpoints tests
@pytest.mark.asyncio
async def test_get_users_success(client: AsyncClient, auth_headers: Dict[str, str]):
    response = await client.get("/users", headers=auth_headers)
    assert response.status_code == 200
    assert "items" in response.json()

@pytest.mark.asyncio
async def test_create_user_success(client: AsyncClient, auth_headers: Dict[str, str], test_user_data: Dict[str, Any]):
    response = await client.post("/users", json=test_user_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == test_user_data["username"]
    assert "id" in data

@pytest.mark.asyncio
async def test_get_user_by_id_success(client: AsyncClient, auth_headers: Dict[str, str], created_user: Dict[str, Any]):
    user_id = created_user["id"]
    response = await client.get(f"/users/{user_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user_id

@pytest.mark.asyncio
async def test_update_user_success(client: AsyncClient, auth_headers: Dict[str, str], created_user: Dict[str, Any]):
    user_id = created_user["id"]
    update_data = {"full_name": "Updated Full Name"}
    response = await client.put(f"/users/{user_id}", json=update_data, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Updated Full Name"

@pytest.mark.asyncio
async def test_delete_user_success(client: AsyncClient, auth_headers: Dict[str, str], created_user: Dict[str, Any]):
    user_id = created_user["id"]
    response = await client.delete(f"/users/{user_id}", headers=auth_headers)
    assert response.status_code == 200

# Task endpoints tests
@pytest.mark.asyncio
async def test_get_tasks_success(client: AsyncClient, auth_headers: Dict[str, str]):
    response = await client.get("/tasks", headers=auth_headers)
    assert response.status_code == 200
    assert "items" in response.json()

@pytest.mark.asyncio
async def test_get_tasks_with_filters(client: AsyncClient, auth_headers: Dict[str, str], created_project: Dict[str, Any]):
    project_id = created_project["id"]
    response = await client.get(f"/tasks?project_id={project_id}&status={TaskStatusEnum.TODO.value}", headers=auth_headers)
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_create_task_success(client: AsyncClient, auth_headers: Dict[str, str], created_project: Dict[str, Any], test_task_data: Dict[str, Any]):
    task_data = test_task_data.copy()
    task_data["project_id"] = created_project["id"]
    response = await client.post("/tasks", json=task_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == test_task_data["title"]
    assert data["project_id"] == created_project["id"]

@pytest.mark.asyncio
async def test_get_task_by_id_success(client: AsyncClient, auth_headers: Dict[str, str], created_task: Dict[str, Any]):
    task_id = created_task["id"]
    response = await client.get(f"/tasks/{task_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == task_id

@pytest.mark.asyncio
async def test_update_task_success(client: AsyncClient, auth_headers: Dict[str, str], created_task: Dict[str, Any]):
    task_id = created_task["id"]
    update_data = {"title": "Updated Task Title"}
    response = await client.put(f"/tasks/{task_id}", json=update_data, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Task Title"

@pytest.mark.asyncio
async def test_delete_task_success(client: AsyncClient, auth_headers: Dict[str, str], created_task: Dict[str, Any]):
    task_id = created_task["id"]
    response = await client.delete(f"/tasks/{task_id}", headers=auth_headers)
    assert response.status_code == 200

# Project-specific task endpoints
@pytest.mark.asyncio
async def test_get_project_tasks_success(client: AsyncClient, auth_headers: Dict[str, str], created_project: Dict[str, Any], created_task: Dict[str, Any]):
    project_id = created_project["id"]
    response = await client.get(f"/projects/{project_id}/tasks", headers=auth_headers)
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks["items"]) > 0

# Subtask endpoints
@pytest.mark.asyncio
async def test_get_subtasks_success(client: AsyncClient, auth_headers: Dict[str, str], created_task: Dict[str, Any]):
    task_id = created_task["id"]
    response = await client.get(f"/tasks/{task_id}/subtasks", headers=auth_headers)
    assert response.status_code == 200
    assert "items" in response.json()

@pytest.mark.asyncio
async def test_create_subtask_success(client: AsyncClient, auth_headers: Dict[str, str], created_task: Dict[str, Any], test_task_data: Dict[str, Any]):
    task_id = created_task["id"]
    subtask_data = {
        "title": "Subtask Test",
        "description": "A test subtask"
    }
    response = await client.post(f"/tasks/{task_id}/subtasks", json=subtask_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Subtask Test"
    assert data["parent_id"] == task_id

# Tag endpoints
@pytest.mark.asyncio
async def test_get_tags_success(client: AsyncClient, auth_headers: Dict[str, str]):
    response = await client.get("/tags", headers=auth_headers)
    assert response.status_code == 200
    assert "items" in response.json()

@pytest.mark.asyncio
async def test_create_tag_success(client: AsyncClient, auth_headers: Dict[str, str], test_tag_data: Dict[str, Any]):
    response = await client.post("/tags", json=test_tag_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == test_tag_data["name"]

@pytest.mark.asyncio
async def test_get_tag_by_id_success(client: AsyncClient, auth_headers: Dict[str, str], created_tag: Dict[str, Any]):
    tag_id = created_tag["id"]
    response = await client.get(f"/tags/{tag_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == tag_id

@pytest.mark.asyncio
async def test_update_tag_success(client: AsyncClient, auth_headers: Dict[str, str], created_tag: Dict[str, Any]):
    tag_id = created_tag["id"]
    update_data = {"name": "Updated Tag Name"}
    response = await client.put(f"/tags/{tag_id}", json=update_data, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Tag Name"

@pytest.mark.asyncio
async def test_delete_tag_success(client: AsyncClient, auth_headers: Dict[str, str], created_tag: Dict[str, Any]):
    tag_id = created_tag["id"]
    response = await client.delete(f"/tags/{tag_id}", headers=auth_headers)
    assert response.status_code == 200

# Task-tag relationship endpoints
@pytest.mark.asyncio
async def test_get_task_tags_success(client: AsyncClient, auth_headers: Dict[str, str], created_task: Dict[str, Any], created_tag: Dict[str, Any]):
    task_id = created_task["id"]
    tag_id = created_tag["id"]
    # Add tag to task first
    tag_data = {"tag_id": tag_id}
    await client.post(f"/tasks/{task_id}/tags", json=tag_data, headers=auth_headers)
    
    response = await client.get(f"/tasks/{task_id}/tags", headers=auth_headers)
    assert response.status_code == 200
    tags = response.json()
    assert len(tags["items"]) > 0

@pytest.mark.asyncio
async def test_add_tag_to_task_success(client: AsyncClient, auth_headers: Dict[str, str], created_task: Dict[str, Any], created_tag: Dict[str, Any]):
    task_id = created_task["id"]
    tag_id = created_tag["id"]
    tag_data = {"tag_id": tag_id}
    response = await client.post(f"/tasks/{task_id}/tags", json=tag_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["task_id"] == task_id
    assert data["tag_id"] == tag_id

@pytest.mark.asyncio
async def test_remove_tag_from_task_success(client: AsyncClient, auth_headers: Dict[str, str], created_task: Dict[str, Any], created_tag: Dict[str, Any]):
    task_id = created_task["id"]
    tag_id = created_tag["id"]
    # Add tag to task first
    tag_data = {"tag_id": tag_id}
    await client.post(f"/tasks/{task_id}/tags", json=tag_data, headers=auth_headers)
    
    response = await client.delete(f"/tasks/{task_id}/tags/{tag_id}", headers=auth_headers)
    assert response.status_code == 200

# Comment endpoints
@pytest.mark.asyncio
async def test_get_task_comments_success(client: AsyncClient, auth_headers: Dict[str, str], created_task: Dict[str, Any]):
    task_id = created_task["id"]
    response = await client.get(f"/tasks/{task_id}/comments", headers=auth_headers)
    assert response.status_code == 200
    assert "items" in response.json()

@pytest.mark.asyncio
async def test_create_comment_success(client: AsyncClient, auth_headers: Dict[str, str], created_task: Dict[str, Any], test_comment_data: Dict[str, Any]):
    task_id = created_task["id"]
    response = await client.post(f"/tasks/{task_id}/comments", json=test_comment_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["content"] == test_comment_data["content"]
    assert data["task_id"] == task_id

@pytest.mark.asyncio
async def test_get_comment_by_id_success(client: AsyncClient, auth_headers: Dict[str, str], created_task: Dict[str, Any], test_comment_data: Dict[str, Any]):
    task_id = created_task["id"]
    # Create comment first
    create_response = await client.post(f"/tasks/{task_id}/comments", json=test_comment_data, headers=auth_headers)
    comment_id = create_response.json()["id"]
    
    response = await client.get(f"/comments/{comment_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == comment_id

@pytest.mark.asyncio
async def test_update_comment_success(client: AsyncClient, auth_headers: Dict[str, str], created_task: Dict[str, Any], test_comment_data: Dict[str, Any]):
    task_id = created_task["id"]
    # Create comment first
    create_response = await client.post(f"/tasks/{task_id}/comments", json=test_comment_data, headers=auth_headers)
    comment_id = create_response.json()["id"]
    
    update_data = {"content": "Updated comment content"}
    response = await client.put(f"/comments/{comment_id}", json=update_data, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Updated comment content"

@pytest.mark.asyncio
async def test_delete_comment_success(client: AsyncClient, auth_headers: Dict[str, str], created_task: Dict[str, Any], test_comment_data: Dict[str, Any]):
    task_id = created_task["id"]
    # Create comment first
    create_response = await client.post(f"/tasks/{task_id}/comments", json=test_comment_data, headers=auth_headers)
    comment_id = create_response.json()["id"]
    
    response = await client.delete(f"/comments/{comment_id}", headers=auth_headers)
    assert response.status_code == 200

# Attachment endpoints
@pytest.mark.asyncio
async def test_get_task_attachments_success(client: AsyncClient, auth_headers: Dict[str, str], created_task: Dict[str, Any]):
    task_id = created_task["id"]
    response = await client.get(f"/tasks/{task_id}/attachments", headers=auth_headers)
    assert response.status_code == 200
    assert "items" in response.json()

@pytest.mark.asyncio
async def test_create_attachment_success(client: AsyncClient, auth_headers: Dict[str, str], created_task: Dict[str, Any], test_attachment_data: Dict[str, Any]):
    task_id = created_task["id"]
    response = await client.post(f"/tasks/{task_id}/attachments", json=test_attachment_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == test_attachment_data["filename"]
    assert data["task_id"] == task_id

@pytest.mark.asyncio
async def test_get_attachment_by_id_success(client: AsyncClient, auth_headers: Dict[str, str], created_task: Dict[str, Any], test_attachment_data: Dict[str, Any]):
    task_id = created_task["id"]
    # Create attachment first
    create_response = await client.post(f"/tasks/{task_id}/attachments", json=test_attachment_data, headers=auth_headers)
    attachment_id = create_response.json()["id"]
    
    response = await client.get(f"/attachments/{attachment_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == attachment_id

@pytest.mark.asyncio
async def test_delete_attachment_success(client: AsyncClient, auth_headers: Dict[str, str], created_task: Dict[str, Any], test_attachment_data: Dict[str, Any]):
    task_id = created_task["id"]
    # Create attachment first
    create_response = await client.post(f"/tasks/{task_id}/attachments", json=test_attachment_data, headers=auth_headers)
    attachment_id = create_response.json()["id"]
    
    response = await client.delete(f"/attachments/{attachment_id}", headers=auth_headers)
    assert response.status_code == 200

# Boundary condition tests
@pytest.mark.asyncio
async def test_get_projects_invalid_page_size(client: AsyncClient, auth_headers: Dict[str, str]):
    response = await client.get("/projects?page=-1&size=-1", headers=auth_headers)
    # Depending on validation, this might return 422 or clamp to valid values
    # For this test, we assume validation returns 422
    assert response.status_code in [422, 200]

@pytest.mark.asyncio
async def test_create_project_missing_required_fields(client: AsyncClient, auth_headers: Dict[str, str]):
    response = await client.post("/projects", json={}, headers=auth_headers)
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_get_nonexistent_resource(client: AsyncClient, auth_headers: Dict[str, str]):
    response = await client.get("/projects/999999", headers=auth_headers)
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_unauthorized_access(client: AsyncClient):
    # Test without auth headers
    response = await client.get("/projects")
    assert response.status_code in [401, 403]  # Unauthorized or Forbidden