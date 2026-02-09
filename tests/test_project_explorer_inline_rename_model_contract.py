from engine.editor.project_explorer_inline_rename_model import (
    is_renameable_path,
    split_basename_ext,
    compute_initial_rename_text,
    should_commit_rename,
    compute_committed_name_for_path
)

def test_is_renameable_path_allows_folders():
    assert is_renameable_path("assets/sprites", is_dir=True) is True
    assert is_renameable_path("assets", is_dir=True) is True
    assert is_renameable_path("src/lib", is_dir=True) is True
    assert is_renameable_path("src", is_dir=True) is True

def test_is_renameable_path_rejects_root_or_empty():
    assert is_renameable_path("", is_dir=True) is False
    assert is_renameable_path("  ", is_dir=True) is False

def test_compute_initial_rename_text_folders():
    # Folders don't have extensions
    # (stem, ext, basename)
    assert compute_initial_rename_text("assets/sprites", is_dir=True) == ("sprites", "", "sprites")
    assert compute_initial_rename_text("assets.data", is_dir=True) == ("assets.data", "", "assets.data")

def test_compute_initial_rename_text_files():
    # Files preserve extension logic
    assert compute_initial_rename_text("assets/image.png", is_dir=False) == ("image", ".png", "image.png")
    assert compute_initial_rename_text("main.py", is_dir=False) == ("main", ".py", "main.py")

def test_compute_committed_name_folders():
    # Folders: use exact text, no extension appending
    assert compute_committed_name_for_path("assets/sprites", "new_sprites", is_dir=True) == "new_sprites"
    assert compute_committed_name_for_path("assets/old_name", "new.name", is_dir=True) == "new.name"

def test_compute_committed_name_files():
    # Files: append original extension
    assert compute_committed_name_for_path("assets/img.png", "new_img", is_dir=False) == "new_img.png"
    assert compute_committed_name_for_path("assets/img.png", "new.img", is_dir=False) == "new.img.png"

def test_should_commit_rename_folder():
    # Folder renaming scenarios
    # No extension passed
    ok, name, err = should_commit_rename("old", "new_name", is_dir=True)
    assert ok is True
    assert name == "new_name"
    assert err is None

    # Empty
    ok, _, err = should_commit_rename("old", "", is_dir=True)
    assert ok is False
    assert "empty" in err

    # Invalid chars
    ok, _, err = should_commit_rename("old", "bad/name", is_dir=True)
    assert ok is False

def test_should_commit_rename_file():
    # File renaming scenarios (backwards compat)
    # Extension passed via original_ext
    ok, name, err = should_commit_rename("old", "new_name", is_dir=False, original_ext=".png")
    assert ok is True
    assert name == "new_name.png"

    # No extension (e.g. LICENSE)
    ok, name, err = should_commit_rename("LICENSE", "NEW_LICENSE", is_dir=False, original_ext="")
    assert ok is True
    assert name == "NEW_LICENSE"
