from pathlib import Path

from app import create_app
from app.config import Config


def _write_frontend_fixture(frontend_dist: Path) -> tuple[str, str]:
    index_html = "<html><body>Deutsche MiroFish-Oberflaeche</body></html>"
    asset_javascript = "window.mirofishReady = true"

    (frontend_dist / "assets").mkdir()
    (frontend_dist / "index.html").write_text(index_html, encoding="utf-8")
    (frontend_dist / "assets" / "app.js").write_text(
        asset_javascript,
        encoding="utf-8",
    )

    return index_html, asset_javascript


def test_serves_built_frontend_with_spa_fallback_without_masking_api_routes(
    tmp_path,
    monkeypatch,
):
    index_html, asset_javascript = _write_frontend_fixture(tmp_path)
    monkeypatch.setattr(Config, "AUTH_ENABLED", False)

    app = create_app()
    app.config["FRONTEND_DIST"] = str(tmp_path)
    client = app.test_client()

    assert client.get("/").get_data(as_text=True) == index_html
    assert client.get("/simulation/example").get_data(as_text=True) == index_html
    assert client.get("/assets/app.js").get_data(as_text=True) == asset_javascript
    assert client.get("/api/not-a-route").status_code == 404


def test_auth_keeps_frontend_public_and_protects_api(tmp_path, monkeypatch):
    index_html, _ = _write_frontend_fixture(tmp_path)
    monkeypatch.setattr(Config, "AUTH_ENABLED", True)

    app = create_app()
    app.config["FRONTEND_DIST"] = str(tmp_path)
    client = app.test_client()

    frontend_response = client.get("/")
    api_response = client.get("/api/simulation/list")

    assert frontend_response.status_code == 200
    assert frontend_response.get_data(as_text=True) == index_html
    assert api_response.status_code == 401
    assert api_response.get_json() == {
        "success": False,
        "error": "Authentifizierung erforderlich",
    }
