"""Tests for the zettabyte fork additions: CF Access headers + shared env file."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from planecli.config import load_config, save_config
from planecli.exceptions import AuthenticationError

BASE_ENV = {
    "PLANE_BASE_URL": "https://help.example.com",
    "PLANE_API_KEY": "key",
    "PLANE_WORKSPACE": "ws",
}


class TestBaseUrlNormalization:
    @pytest.mark.parametrize(
        "url",
        [
            "https://help.example.com/api/v1",
            "https://help.example.com/api/v1/",
            "https://help.example.com/",
            "https://help.example.com",
        ],
    )
    def test_strips_trailing_api_v1(self, tmp_path, url):
        env = {**BASE_ENV, "PLANE_BASE_URL": url}
        with (
            patch("planecli.config.CONFIG_FILE", tmp_path / "nonexistent"),
            patch.dict("os.environ", env, clear=True),
        ):
            config = load_config()
        assert config.base_url == "https://help.example.com"


class TestWorkspaceSlugAlias:
    def test_plane_workspace_slug_env_accepted(self, tmp_path):
        env = {
            "PLANE_BASE_URL": "https://help.example.com",
            "PLANE_API_KEY": "key",
            "PLANE_WORKSPACE_SLUG": "slug-ws",
        }
        with (
            patch("planecli.config.CONFIG_FILE", tmp_path / "nonexistent"),
            patch.dict("os.environ", env, clear=True),
        ):
            config = load_config()
        assert config.workspace == "slug-ws"

    def test_plane_workspace_wins_over_slug(self, tmp_path):
        env = {**BASE_ENV, "PLANE_WORKSPACE_SLUG": "slug-ws"}
        with (
            patch("planecli.config.CONFIG_FILE", tmp_path / "nonexistent"),
            patch.dict("os.environ", env, clear=True),
        ):
            config = load_config()
        assert config.workspace == "ws"


class TestCfAccessConfig:
    def test_from_env_vars(self, tmp_path):
        env = {**BASE_ENV, "CF_ACCESS_CLIENT_ID": "cf-id", "CF_ACCESS_CLIENT_SECRET": "cf-secret"}
        with (
            patch("planecli.config.CONFIG_FILE", tmp_path / "nonexistent"),
            patch.dict("os.environ", env, clear=True),
        ):
            config = load_config()
        assert config.cf_access_client_id == "cf-id"
        assert config.cf_access_client_secret == "cf-secret"

    def test_absent_by_default(self, tmp_path):
        with (
            patch("planecli.config.CONFIG_FILE", tmp_path / "nonexistent"),
            patch.dict("os.environ", BASE_ENV, clear=True),
        ):
            config = load_config()
        assert config.cf_access_client_id is None
        assert config.cf_access_client_secret is None

    def test_from_config_file(self, tmp_path):
        config_file = tmp_path / ".plane_api"
        config_file.write_text(
            "base_url=https://help.example.com\napi_key=key\nworkspace=ws\n"
            "cf_access_client_id=file-id\ncf_access_client_secret=file-secret\n"
        )
        with (
            patch("planecli.config.CONFIG_FILE", config_file),
            patch.dict("os.environ", {}, clear=True),
        ):
            config = load_config()
        assert config.cf_access_client_id == "file-id"
        assert config.cf_access_client_secret == "file-secret"

    def test_save_config_persists_cf_fields(self, tmp_path):
        config_file = tmp_path / ".plane_api"
        with patch("planecli.config.CONFIG_FILE", config_file):
            save_config("https://help.example.com", "key", "ws", "cf-id", "cf-secret")
        content = config_file.read_text()
        assert "cf_access_client_id=cf-id" in content
        assert "cf_access_client_secret=cf-secret" in content


class TestSharedEnvFile:
    def _write_env_file(self, tmp_path):
        env_file = tmp_path / "plane.env"
        env_file.write_text(
            "CF_ACCESS_CLIENT_ID=envfile-id\n"
            "CF_ACCESS_CLIENT_SECRET=envfile-secret\n"
            "PLANE_API_KEY=envfile-key\n"
            "PLANE_BASE_URL=https://help.example.com/api/v1\n"
            "PLANE_WORKSPACE_SLUG=envfile-ws\n"
        )
        return env_file

    def test_full_config_from_env_file(self, tmp_path):
        env_file = self._write_env_file(tmp_path)
        with (
            patch("planecli.config.CONFIG_FILE", tmp_path / "nonexistent"),
            patch("planecli.config.DEFAULT_ENV_FILE", env_file),
            patch.dict("os.environ", {}, clear=True),
        ):
            config = load_config()
        assert config.base_url == "https://help.example.com"
        assert config.api_key == "envfile-key"
        assert config.workspace == "envfile-ws"
        assert config.cf_access_client_id == "envfile-id"
        assert config.cf_access_client_secret == "envfile-secret"

    def test_plane_env_file_var_selects_file(self, tmp_path):
        env_file = self._write_env_file(tmp_path)
        with (
            patch("planecli.config.CONFIG_FILE", tmp_path / "nonexistent"),
            patch.dict("os.environ", {"PLANE_ENV_FILE": str(env_file)}, clear=True),
        ):
            config = load_config()
        assert config.api_key == "envfile-key"

    def test_config_file_wins_over_env_file(self, tmp_path):
        env_file = self._write_env_file(tmp_path)
        config_file = tmp_path / ".plane_api"
        config_file.write_text("base_url=https://other.example.com\napi_key=file-key\n")
        with (
            patch("planecli.config.CONFIG_FILE", config_file),
            patch("planecli.config.DEFAULT_ENV_FILE", env_file),
            patch.dict("os.environ", {}, clear=True),
        ):
            config = load_config()
        assert config.base_url == "https://other.example.com"
        assert config.api_key == "file-key"
        # workspace only present in the env file — still resolved from there
        assert config.workspace == "envfile-ws"

    def test_missing_env_file_still_errors(self, tmp_path):
        with (
            patch("planecli.config.CONFIG_FILE", tmp_path / "nonexistent"),
            patch("planecli.config.DEFAULT_ENV_FILE", tmp_path / "nonexistent.env"),
            patch.dict("os.environ", {}, clear=True),
        ):
            with pytest.raises(AuthenticationError, match="Missing base URL"):
                load_config()


class TestHeaderInjection:
    def _make_resource(self):
        from plane.api.base_resource import BaseResource
        from plane.config import Configuration

        config = Configuration(base_path="https://help.example.com", api_key="key")
        return BaseResource(config, "/x")

    def test_cf_headers_added_when_configured(self):
        import planecli.api.client as client_mod
        from planecli.config import Config

        resource = self._make_resource()
        cfg = Config(
            base_url="https://help.example.com",
            api_key="key",
            workspace="ws",
            cf_access_client_id="cf-id",
            cf_access_client_secret="cf-secret",
        )
        with patch.object(client_mod, "_config", cfg):
            headers = resource._headers()
        assert headers["CF-Access-Client-Id"] == "cf-id"
        assert headers["CF-Access-Client-Secret"] == "cf-secret"
        assert headers["X-Api-Key"] == "key"

    def test_no_cf_headers_when_not_configured(self):
        import planecli.api.client as client_mod
        from planecli.config import Config

        resource = self._make_resource()
        cfg = Config(base_url="https://help.example.com", api_key="key", workspace="ws")
        with patch.object(client_mod, "_config", cfg):
            headers = resource._headers()
        assert "CF-Access-Client-Id" not in headers
        assert "CF-Access-Client-Secret" not in headers
