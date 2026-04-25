"""Tests for authentication and authorization system."""

from datetime import UTC, datetime, timedelta

import pytest

from pms.models.api_key import ApiKey, generate_api_key, hash_api_key
from pms.repositories.api_key_repository import ApiKeyRepository
from pms.services.auth_service import AuthService


class TestApiKeyModel:
    """Test API key model and utilities."""

    def test_generate_api_key(self):
        """Test API key generation produces valid keys."""
        plain_key, key_hash = generate_api_key()

        # Key should start with pms_ prefix
        assert plain_key.startswith("pms_")

        # Key should be long enough (prefix + 32 bytes base64 ~= 55 chars)
        assert len(plain_key) > 40

        # Hash should be different from plain key
        assert key_hash != plain_key

        # Hash should be consistent
        assert hash_api_key(plain_key) == key_hash

    def test_api_key_validation(self):
        """Test API key validity checks."""
        now = datetime.now(UTC)

        # Valid active key
        key = ApiKey(
            id="apikey_test1",
            name="Test Key",
            key_hash="hash123",
            prefix="pms_abc",
            created_at=now,
            expires_at=None,
            last_used_at=None,
            is_active=True,
            scopes=["*"],
            metadata={},
            rate_limit=None,
        )
        assert key.is_valid

        # Inactive key
        key.is_active = False
        assert not key.is_valid

        # Expired key
        key.is_active = True
        key.expires_at = now - timedelta(days=1)
        assert not key.is_valid

    def test_scope_matching(self):
        """Test scope matching logic."""
        key = ApiKey(
            id="apikey_test1",
            name="Test Key",
            key_hash="hash123",
            prefix="pms_abc",
            created_at=datetime.now(UTC),
            expires_at=None,
            last_used_at=None,
            is_active=True,
            scopes=["tasks:read", "tasks:write", "products:*"],
            metadata={},
            rate_limit=None,
        )

        # Exact matches
        assert key.matches_scope("tasks:read")
        assert key.matches_scope("tasks:write")

        # Wildcard matches
        assert key.matches_scope("products:read")
        assert key.matches_scope("products:write")
        assert key.matches_scope("products:delete")

        # No match
        assert not key.matches_scope("projects:read")
        assert not key.matches_scope("admin:keys")

        # Admin key with *
        admin_key = ApiKey(
            id="apikey_admin",
            name="Admin Key",
            key_hash="hash456",
            prefix="pms_xyz",
            created_at=datetime.now(UTC),
            expires_at=None,
            last_used_at=None,
            is_active=True,
            scopes=["*"],
            metadata={},
            rate_limit=None,
        )

        # Admin key matches everything
        assert admin_key.matches_scope("tasks:read")
        assert admin_key.matches_scope("products:write")
        assert admin_key.matches_scope("admin:keys")
        assert admin_key.matches_scope("anything:else")

    def test_row_level_scope_matching(self):
        """Test row-level (hierarchical) scope matching."""
        now = datetime.now(UTC)
        project_id_primary = "6c4c7184-b537-489a-a5c1-ecdc4c2f6935"
        project_id_other = "b5df40d4-7f07-4e02-8aa4-b3f473c98d18"
        project_id_third = "8f685ac1-4606-4f4e-b0e9-3a10fbd017e0"
        task_id_primary = "f14aa66c-1f7e-44af-b12b-6c55f55f4d1d"
        task_id_other = "78a27776-a8aa-4edc-b731-f259cd16610d"

        # Test 1: Specific project access
        project_key = ApiKey(
            id="apikey_proj",
            name="Project-Specific Key",
            key_hash="hash123",
            prefix="pms_abc",
            created_at=now,
            expires_at=None,
            last_used_at=None,
            is_active=True,
            scopes=[
                f"project:{project_id_primary}:read",
                f"project:{project_id_primary}:write",
            ],
            metadata={},
            rate_limit=None,
        )

        # Can access specific project
        assert project_key.matches_scope(f"project:{project_id_primary}:read")
        assert project_key.matches_scope(f"project:{project_id_primary}:write")

        # Cannot access different project
        assert not project_key.matches_scope(f"project:{project_id_other}:read")
        assert not project_key.matches_scope(f"project:{project_id_other}:write")

        # Cannot access without specifying project (resource-level)
        assert not project_key.matches_scope("project:read")

        # Test 2: Wildcard at resource ID level
        any_project_read = ApiKey(
            id="apikey_anyproj",
            name="Any Project Read",
            key_hash="hash456",
            prefix="pms_xyz",
            created_at=now,
            expires_at=None,
            last_used_at=None,
            is_active=True,
            scopes=["project:*:read"],
            metadata={},
            rate_limit=None,
        )

        # Can read any project
        assert any_project_read.matches_scope(f"project:{project_id_primary}:read")
        assert any_project_read.matches_scope(f"project:{project_id_other}:read")
        assert any_project_read.matches_scope(f"project:{project_id_third}:read")

        # Cannot write
        assert not any_project_read.matches_scope(f"project:{project_id_primary}:write")

        # Test 3: Wildcard at operation level
        project_full_access = ApiKey(
            id="apikey_projfull",
            name="Project Full Access",
            key_hash="hash789",
            prefix="pms_def",
            created_at=now,
            expires_at=None,
            last_used_at=None,
            is_active=True,
            scopes=[f"project:{project_id_primary}:*"],
            metadata={},
            rate_limit=None,
        )

        # Can do anything on specific project
        assert project_full_access.matches_scope(f"project:{project_id_primary}:read")
        assert project_full_access.matches_scope(f"project:{project_id_primary}:write")
        assert project_full_access.matches_scope(f"project:{project_id_primary}:delete")

        # Cannot access other projects
        assert not project_full_access.matches_scope(f"project:{project_id_other}:read")

        # Test 4: Task-level access
        task_key = ApiKey(
            id="apikey_task",
            name="Single Task Key",
            key_hash="hash999",
            prefix="pms_ghi",
            created_at=now,
            expires_at=None,
            last_used_at=None,
            is_active=True,
            scopes=[f"task:{task_id_primary}:write"],
            metadata={},
            rate_limit=None,
        )

        # Can write to specific task
        assert task_key.matches_scope(f"task:{task_id_primary}:write")

        # Cannot read (only granted write)
        assert not task_key.matches_scope(f"task:{task_id_primary}:read")

        # Cannot access other tasks
        assert not task_key.matches_scope(f"task:{task_id_other}:write")

        # Test 5: Resource-level wildcard still works
        tasks_all = ApiKey(
            id="apikey_tasks",
            name="All Tasks",
            key_hash="hash888",
            prefix="pms_jkl",
            created_at=now,
            expires_at=None,
            last_used_at=None,
            is_active=True,
            scopes=["tasks:*"],  # Resource-level wildcard
            metadata={},
            rate_limit=None,
        )

        # Matches resource-level access
        assert tasks_all.matches_scope("tasks:read")
        assert tasks_all.matches_scope("tasks:write")

        # Also matches row-level access through wildcard expansion
        assert tasks_all.matches_scope(f"tasks:{task_id_primary}:read")
        assert tasks_all.matches_scope(f"tasks:{task_id_other}:write")

        # Test 6: Multi-level hierarchy
        product_feature_key = ApiKey(
            id="apikey_feature",
            name="Product Feature Key",
            key_hash="hash777",
            prefix="pms_mno",
            created_at=now,
            expires_at=None,
            last_used_at=None,
            is_active=True,
            scopes=[
                "product:6c4c7184-b537-489a-a5c1-ecdc4c2f6935:"
                "feature:f14aa66c-1f7e-44af-b12b-6c55f55f4d1d:read"
            ],
            metadata={},
            rate_limit=None,
        )

        # Can access specific feature of specific product
        assert product_feature_key.matches_scope(
            "product:6c4c7184-b537-489a-a5c1-ecdc4c2f6935:"
            "feature:f14aa66c-1f7e-44af-b12b-6c55f55f4d1d:read"
        )

        # Cannot access different feature
        assert not product_feature_key.matches_scope(
            "product:6c4c7184-b537-489a-a5c1-ecdc4c2f6935:"
            "feature:78a27776-a8aa-4edc-b731-f259cd16610d:read"
        )

        # Cannot write
        assert not product_feature_key.matches_scope(
            "product:6c4c7184-b537-489a-a5c1-ecdc4c2f6935:"
            "feature:f14aa66c-1f7e-44af-b12b-6c55f55f4d1d:write"
        )


@pytest.mark.asyncio
class TestAuthService:
    """Test authentication service."""

    async def test_create_api_key(self, test_db):
        """Test creating an API key."""
        repo = ApiKeyRepository(test_db)
        service = AuthService(repo)

        plain_key, api_key = await service.create_api_key(
            name="Test Key",
            scopes=["tasks:read", "tasks:write"],
            expires_in_days=30,
            rate_limit=100,
            metadata={"env": "test"},
        )

        # Verify plain key format
        assert plain_key.startswith("pms_")
        assert len(plain_key) > 40

        # Verify stored key
        assert api_key.name == "Test Key"
        assert api_key.scopes == ["tasks:read", "tasks:write"]
        assert api_key.is_active
        assert api_key.rate_limit == 100
        assert api_key.metadata == {"env": "test"}
        assert api_key.expires_at is not None

        # Verify key can be retrieved
        retrieved = await repo.get_by_hash(hash_api_key(plain_key))
        assert retrieved is not None
        assert retrieved.id == api_key.id

    async def test_validate_api_key(self, test_db):
        """Test API key validation."""
        repo = ApiKeyRepository(test_db)
        service = AuthService(repo)

        # Create a key
        plain_key, _ = await service.create_api_key(
            name="Validation Test",
            scopes=["tasks:read", "products:write"],
        )

        # Valid key without scope check
        result = await service.validate_api_key(plain_key)
        assert result is not None
        assert result.name == "Validation Test"

        # Valid key with matching scope
        result = await service.validate_api_key(plain_key, "tasks:read")
        assert result is not None

        # Valid key with non-matching scope
        result = await service.validate_api_key(plain_key, "admin:keys")
        assert result is None

        # Invalid key
        result = await service.validate_api_key("pms_invalid_key_123")
        assert result is None

    async def test_deactivate_key(self, test_db):
        """Test deactivating an API key."""
        repo = ApiKeyRepository(test_db)
        service = AuthService(repo)

        # Create and deactivate key
        plain_key, api_key = await service.create_api_key(
            name="Deactivate Test",
            scopes=["*"],
        )

        await service.deactivate_key(api_key.id)

        # Should no longer validate
        result = await service.validate_api_key(plain_key)
        assert result is None

    async def test_restore_key_reactivates_archived_inactive_key(self, test_db):
        """Restoring an archived inactive key should reactivate it atomically."""
        repo = ApiKeyRepository(test_db)
        service = AuthService(repo)

        _, api_key = await service.create_api_key(
            name="Restore Me",
            scopes=["*"],
        )
        await service.deactivate_key(api_key.id)
        await service.delete_key(api_key.id)

        restored = await service.restore_key(api_key.id)

        assert restored is not None
        assert restored.is_active is True
        assert restored.archived_at is None

        row = await test_db.fetch_one(
            "SELECT archived_at, is_active FROM api_keys WHERE id = ?",
            (api_key.id,),
        )
        assert row is not None
        assert row["archived_at"] is None
        assert row["is_active"] == 1

    async def test_restore_key_rolls_back_restore_when_reactivate_fails(
        self, test_db, monkeypatch
    ):
        """Restore/reactivate should not leave a key half-restored if reactivation fails."""
        repo = ApiKeyRepository(test_db)
        service = AuthService(repo)

        _, api_key = await service.create_api_key(
            name="Rollback Restore",
            scopes=["*"],
        )
        await service.deactivate_key(api_key.id)
        await service.delete_key(api_key.id)

        async def fail_reactivate(key_id: str):
            raise RuntimeError(f"boom while reactivating {key_id}")

        monkeypatch.setattr(repo, "reactivate", fail_reactivate)

        with pytest.raises(RuntimeError, match="boom while reactivating"):
            await service.restore_key(api_key.id)

        row = await test_db.fetch_one(
            "SELECT archived_at, is_active FROM api_keys WHERE id = ?",
            (api_key.id,),
        )
        assert row is not None
        assert row["archived_at"] is not None
        assert row["is_active"] == 0

    async def test_rate_limiting(self, test_db):
        """Test rate limiting enforcement."""
        repo = ApiKeyRepository(test_db)
        service = AuthService(repo)

        # Create key with low rate limit
        plain_key, api_key = await service.create_api_key(
            name="Rate Limited",
            scopes=["*"],
            rate_limit=3,  # 3 requests per minute
        )

        # First 3 requests should succeed
        for i in range(3):
            allowed, count, limit = await service.check_rate_limit(api_key)
            assert allowed
            assert limit == 3
            assert count == i + 1

        # 4th request should fail
        allowed, count, limit = await service.check_rate_limit(api_key)
        assert not allowed
        assert count == 3
        assert limit == 3

    async def test_cleanup_old_rate_limits(self, test_db):
        """Test cleanup of old rate limit data."""
        repo = ApiKeyRepository(test_db)
        service = AuthService(repo)

        # Create key and hit rate limit
        _, api_key = await service.create_api_key(
            name="Cleanup Test",
            scopes=["*"],
            rate_limit=10,
        )

        await service.check_rate_limit(api_key)

        # Cleanup old data (should not affect recent usage)
        deleted = await service.cleanup_old_rate_limits(hours=24)
        assert deleted >= 0


@pytest.mark.asyncio
class TestAuthEndpoints:
    """Test authentication API endpoints."""

    async def test_create_key_requires_admin(self, test_client, admin_api_key):
        """Test creating API key requires admin scope."""
        # Without auth - should fail
        response = test_client.post(
            "/api/v1/auth/keys",
            json={"name": "Test Key", "scopes": ["tasks:read"]},
        )
        assert response.status_code == 401

        # With admin key - should succeed
        response = test_client.post(
            "/api/v1/auth/keys",
            json={"name": "Test Key", "scopes": ["tasks:read"]},
            headers={"X-API-Key": admin_api_key},
        )
        assert response.status_code == 201
        data = response.json()
        assert "api_key" in data
        assert data["api_key"].startswith("pms_")
        assert "key_info" in data
        assert data["key_info"]["name"] == "Test Key"

    async def test_list_keys_requires_admin(self, test_client, admin_api_key):
        """Test listing API keys requires admin scope."""
        # Without auth - should fail
        response = test_client.get("/api/v1/auth/keys")
        assert response.status_code == 401

        # With admin key - should succeed
        response = test_client.get(
            "/api/v1/auth/keys",
            headers={"X-API-Key": admin_api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1  # At least the admin key

    async def test_get_available_scopes(self, test_client):
        """Test getting available scopes (public endpoint)."""
        response = test_client.get("/api/v1/auth/scopes")
        assert response.status_code == 200
        data = response.json()
        assert "scopes" in data
        assert len(data["scopes"]) > 0

        # Check some expected scopes
        assert "tasks:read" in data["scopes"]
        assert "tasks:write" in data["scopes"]
        assert "products:read" in data["scopes"]

    async def test_restore_key_reactivates_archived_inactive_key(
        self, test_client, test_db, admin_api_key
    ):
        """Restore endpoint should unarchive and reactivate the API key."""
        repo = ApiKeyRepository(test_db)
        service = AuthService(repo)

        _, api_key = await service.create_api_key(
            name="Restore Endpoint",
            scopes=["tasks:read"],
        )
        await service.deactivate_key(api_key.id)
        await service.delete_key(api_key.id)

        response = test_client.post(
            f"/api/v1/auth/keys/{api_key.id}/restore",
            headers={"X-API-Key": admin_api_key},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == api_key.id
        assert payload["is_active"] is True
        assert payload["archived_at"] is None


@pytest.mark.asyncio
class TestProtectedEndpoints:
    """Test auth enforcement on protected endpoints."""

    async def test_projects_require_auth(self, test_client, admin_api_key):
        """Test project endpoints require authentication."""
        # List projects without auth
        response = test_client.get("/api/v1/projects")
        assert response.status_code == 401

        # List projects with auth
        response = test_client.get(
            "/api/v1/projects",
            headers={"X-API-Key": admin_api_key},
        )
        assert response.status_code == 200

    async def test_tasks_require_auth(self, test_client, admin_api_key):
        """Test task endpoints require authentication."""
        # List tasks without auth
        response = test_client.get("/api/v1/tasks")
        assert response.status_code == 401

        # List tasks with auth
        response = test_client.get(
            "/api/v1/tasks",
            headers={"X-API-Key": admin_api_key},
        )
        assert response.status_code == 200

    async def test_scope_enforcement(self, test_client, test_db):
        """Test scope-based access control."""
        # Create a read-only key
        repo = ApiKeyRepository(test_db)
        service = AuthService(repo)

        readonly_key, _ = await service.create_api_key(
            name="Read Only",
            scopes=["tasks:read", "projects:read"],
        )

        # Can read tasks
        response = test_client.get(
            "/api/v1/tasks",
            headers={"X-API-Key": readonly_key},
        )
        assert response.status_code == 200

        # Cannot create tasks (needs tasks:write)
        response = test_client.post(
            "/api/v1/tasks",
            json={
                "project_id": "6c4c7184-b537-489a-a5c1-ecdc4c2f6935",
                "title": "Test Task",
                "priority": "medium",
            },
            headers={"X-API-Key": readonly_key},
        )
        assert response.status_code == 403

    async def test_invalid_key_rejected(self, test_client):
        """Test invalid API keys are rejected."""
        response = test_client.get(
            "/api/v1/projects",
            headers={"X-API-Key": "pms_invalid_key_12345"},
        )
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    async def test_rate_limit_enforcement(self, test_client, test_db):
        """Test rate limiting on API endpoints."""
        # Create key with very low rate limit
        repo = ApiKeyRepository(test_db)
        service = AuthService(repo)

        limited_key, _ = await service.create_api_key(
            name="Rate Limited",
            scopes=["*"],
            rate_limit=2,  # Only 2 requests per minute
        )

        # First 2 requests should succeed
        for _ in range(2):
            response = test_client.get(
                "/api/v1/projects",
                headers={"X-API-Key": limited_key},
            )
            assert response.status_code == 200

        # 3rd request should be rate limited
        response = test_client.get(
            "/api/v1/projects",
            headers={"X-API-Key": limited_key},
        )
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["detail"]


@pytest.mark.asyncio
class TestRowLevelAccessControl:
    """Test row-level access control enforcement on API endpoints."""

    async def test_project_specific_access(self, test_client, test_db, admin_api_key):
        """Test that project-specific keys only access their project."""
        # Create two projects as admin
        proj1 = test_client.post(
            "/api/v1/projects",
            json={"name": "Project 1"},
            headers={"X-API-Key": admin_api_key},
        )
        assert proj1.status_code == 201
        proj1_id = proj1.json()["id"]

        proj2 = test_client.post(
            "/api/v1/projects",
            json={"name": "Project 2"},
            headers={"X-API-Key": admin_api_key},
        )
        assert proj2.status_code == 201
        proj2_id = proj2.json()["id"]

        # Create a key that can only read Project 1
        repo = ApiKeyRepository(test_db)
        service = AuthService(repo)

        proj1_key, _ = await service.create_api_key(
            name="Project 1 Read Only",
            scopes=[f"projects:{proj1_id}:read"],
        )

        # Can read Project 1
        response = test_client.get(
            f"/api/v1/projects/{proj1_id}",
            headers={"X-API-Key": proj1_key},
        )
        assert response.status_code == 200
        assert response.json()["id"] == proj1_id

        # Cannot write to Project 1 (only has read)
        response = test_client.patch(
            f"/api/v1/projects/{proj1_id}",
            json={"description": "Updated"},
            headers={"X-API-Key": proj1_key},
        )
        assert response.status_code == 403

        # Cannot read Project 2
        response = test_client.get(
            f"/api/v1/projects/{proj2_id}",
            headers={"X-API-Key": proj1_key},
        )
        assert response.status_code == 403

    async def test_task_specific_access(self, test_client, test_db, admin_api_key):
        """Test that task-specific keys only access their task."""
        # Create project and two tasks
        proj = test_client.post(
            "/api/v1/projects",
            json={"name": "Task Test Project"},
            headers={"X-API-Key": admin_api_key},
        )
        proj_id = proj.json()["id"]

        task1 = test_client.post(
            "/api/v1/tasks",
            json={"project_id": proj_id, "title": "Task 1", "priority": "medium"},
            headers={"X-API-Key": admin_api_key},
        )
        task1_id = task1.json()["id"]

        task2 = test_client.post(
            "/api/v1/tasks",
            json={"project_id": proj_id, "title": "Task 2", "priority": "medium"},
            headers={"X-API-Key": admin_api_key},
        )
        task2_id = task2.json()["id"]

        # Create a key that can write to Task 1 only
        repo = ApiKeyRepository(test_db)
        service = AuthService(repo)

        task1_key, _ = await service.create_api_key(
            name="Task 1 Write",
            scopes=[f"tasks:{task1_id}:write"],
        )

        # Can update Task 1
        response = test_client.patch(
            f"/api/v1/tasks/{task1_id}",
            json={"description": "Updated Task 1"},
            headers={"X-API-Key": task1_key},
        )
        assert response.status_code == 200

        # Cannot update Task 2
        response = test_client.patch(
            f"/api/v1/tasks/{task2_id}",
            json={"description": "Updated Task 2"},
            headers={"X-API-Key": task1_key},
        )
        assert response.status_code == 403

    async def test_wildcard_row_level_access(self, test_client, test_db, admin_api_key):
        """Test wildcard at row level (e.g., project:*:read)."""
        # Create two projects
        proj1 = test_client.post(
            "/api/v1/projects",
            json={"name": "Project A"},
            headers={"X-API-Key": admin_api_key},
        )
        proj1_id = proj1.json()["id"]

        proj2 = test_client.post(
            "/api/v1/projects",
            json={"name": "Project B"},
            headers={"X-API-Key": admin_api_key},
        )
        proj2_id = proj2.json()["id"]

        # Create a key that can read ANY project
        repo = ApiKeyRepository(test_db)
        service = AuthService(repo)

        read_all_projects_key, _ = await service.create_api_key(
            name="Read All Projects",
            scopes=["projects:*:read"],
        )

        # Can read Project 1
        response = test_client.get(
            f"/api/v1/projects/{proj1_id}",
            headers={"X-API-Key": read_all_projects_key},
        )
        assert response.status_code == 200

        # Can read Project 2
        response = test_client.get(
            f"/api/v1/projects/{proj2_id}",
            headers={"X-API-Key": read_all_projects_key},
        )
        assert response.status_code == 200

        # Cannot write to any project
        response = test_client.patch(
            f"/api/v1/projects/{proj1_id}",
            json={"description": "Try to update"},
            headers={"X-API-Key": read_all_projects_key},
        )
        assert response.status_code == 403

    async def test_full_access_to_specific_resource(
        self, test_client, test_db, admin_api_key
    ):
        """Test wildcard at operation level (e.g., project:<project-id>:*)."""
        # Create a project
        proj = test_client.post(
            "/api/v1/projects",
            json={"name": "Full Access Project"},
            headers={"X-API-Key": admin_api_key},
        )
        proj_id = proj.json()["id"]

        # Create a key with full access to this specific project
        repo = ApiKeyRepository(test_db)
        service = AuthService(repo)

        full_access_key, _ = await service.create_api_key(
            name="Project Full Access",
            scopes=[f"projects:{proj_id}:*"],
        )

        # Can read
        response = test_client.get(
            f"/api/v1/projects/{proj_id}",
            headers={"X-API-Key": full_access_key},
        )
        assert response.status_code == 200

        # Can write
        response = test_client.patch(
            f"/api/v1/projects/{proj_id}",
            json={"description": "Updated!"},
            headers={"X-API-Key": full_access_key},
        )
        assert response.status_code == 200

        # Can delete (if delete endpoint exists)
        # Note: Testing the concept - actual delete might not be implemented
        # response = test_client.delete(
        #     f"/api/v1/projects/{proj_id}",
        #     headers={"X-API-Key": full_access_key},
        # )
        # assert response.status_code in [200, 204, 404]  # 404 if endpoint doesn't exist
