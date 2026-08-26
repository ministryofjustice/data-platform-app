"""Tests for MCP server wiring."""

import json
import os
import uuid

import pytest

from data_platform_mcp.server import DataPlatformMCPServer, _get_current_user


@pytest.mark.django_db
class TestGetCurrentUser:
    """Tests for _get_current_user identity resolution."""

    @pytest.fixture
    def user(self, db):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        return User.objects.create_user(oid=uuid.uuid4(), email="mcp@example.com")

    def test_returns_user_by_email(self, user, monkeypatch):
        monkeypatch.setenv("MCP_USER_EMAIL", "mcp@example.com")
        result = _get_current_user()
        assert result.email == "mcp@example.com"

    def test_raises_when_env_var_not_set(self, monkeypatch):
        monkeypatch.delenv("MCP_USER_EMAIL", raising=False)
        with pytest.raises(RuntimeError, match="MCP_USER_EMAIL"):
            _get_current_user()

    def test_raises_when_user_not_found(self, monkeypatch):
        monkeypatch.setenv("MCP_USER_EMAIL", "nobody@example.com")
        with pytest.raises(RuntimeError, match="No user found"):
            _get_current_user()


class TestDataPlatformMCPServerInstantiation:
    """Smoke tests for server instantiation and tool/resource registration."""

    def test_server_instantiates(self):
        server = DataPlatformMCPServer()
        assert server.server is not None

    def test_server_name(self):
        server = DataPlatformMCPServer()
        assert server.server.name == "data-platform"
