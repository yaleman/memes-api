import re
import pytest
from memes_api.config import MemeConfig, meme_config_load


def test_meme_config_load() -> None:
    print("testing None")
    assert isinstance(meme_config_load(None), MemeConfig)
    print("testing specifying path")
    assert isinstance(meme_config_load("tests/test_config.json"), MemeConfig)
    with pytest.raises(FileNotFoundError):
        meme_config_load("non_existent_file.json")
    # test the fallback loader
    assert isinstance(meme_config_load(None), MemeConfig)
    # Clear the cache to test the FileNotFoundError case
    meme_config_load.cache_clear()

    # Monkeypatch the CONFIG_FILES to contain a non-existent file
    print("testing monkeypatch'd config_files to show a FileNotFoundError")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("memes_api.config.CONFIG_FILES", ["asdfsdfadf"])
    with pytest.raises(
        FileNotFoundError, match=re.escape("Couldn't find config at ['asdfsdfadf']")
    ):
        meme_config_load(None)
    monkeypatch.undo()

    meme_config_load.cache_clear()
