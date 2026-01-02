import subprocess
from pathlib import Path


def _git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=str(cwd), text=True).strip()


def test_deploy_public_dir_to_pages_local_remote(tmp_path):
    public_dir = tmp_path / "public"
    public_dir.mkdir()
    (public_dir / "index.html").write_text("<h1>Hello</h1>", encoding="utf-8")

    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True)

    from packages.worker.build.pages import (
        PagesDeployConfig,
        deploy_public_dir_to_pages,
    )

    commit1 = deploy_public_dir_to_pages(
        public_dir=public_dir,
        workdir=tmp_path,
        config=PagesDeployConfig(remote_url=str(remote), branch="gh-pages"),
    )
    assert commit1

    # Deploy again without changes -> commit stays the same.
    commit2 = deploy_public_dir_to_pages(
        public_dir=public_dir,
        workdir=tmp_path,
        config=PagesDeployConfig(remote_url=str(remote), branch="gh-pages"),
    )
    assert commit2 == commit1

    # Verify remote branch contains site files.
    checkout = tmp_path / "checkout"
    subprocess.run(["git", "clone", str(remote), str(checkout)], check=True)
    _git(checkout, "checkout", "gh-pages")
    assert (checkout / "index.html").read_text(encoding="utf-8") == "<h1>Hello</h1>"
    assert (checkout / ".nojekyll").exists()
