import app.config


def test_config_import_smoke():
    assert app.config.CATALOG
    assert app.config.CHAT_MODEL
