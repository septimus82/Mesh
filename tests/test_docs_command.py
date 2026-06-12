import pytest

from engine.tooling import docs_command


class TestDocsCommand:
    @pytest.fixture
    def temp_docs_dir(self, tmp_path):
        """Create a temporary docs directory."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        generated_dir = docs_dir / "generated"
        # generated_dir.mkdir() # docs_command creates it

        return docs_dir, generated_dir

    def test_generate_docs(self, temp_docs_dir):
        """Test that docs are generated."""
        docs_dir, generated_dir = temp_docs_dir

        # Run generation with explicit output dir
        ret = docs_command.main(["--out", str(generated_dir)])
        assert ret == 0

        # Check if files were created
        assert (generated_dir / "commands.md").exists()
        assert (generated_dir / "recipes.md").exists()

        # Check content
        content = (generated_dir / "commands.md").read_text(encoding="utf-8")
        assert "# Mesh CLI Commands" in content

    def test_verify_docs_success(self, temp_docs_dir):
        """Test verification passes when docs are up to date."""
        docs_dir, generated_dir = temp_docs_dir

        # First generate
        docs_command.main(["--out", str(generated_dir)])

        # Then verify
        ret = docs_command.main(["--out", str(generated_dir), "--verify"])
        assert ret == 0

    def test_verify_docs_failure(self, temp_docs_dir):
        """Test verification fails when docs are outdated."""
        docs_dir, generated_dir = temp_docs_dir

        # First generate
        docs_command.main(["--out", str(generated_dir)])

        # Modify a file
        (generated_dir / "commands.md").write_text("Old content", encoding="utf-8")

        # Then verify
        ret = docs_command.main(["--out", str(generated_dir), "--verify"])
        assert ret == 1
