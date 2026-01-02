from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class PagesDeployConfig:
    remote_url: str
    branch: str = "gh-pages"
    cname: str | None = None
    force: bool = False
    git_user_name: str = "ghost-bot"
    git_user_email: str = "ghost-bot@users.noreply.github.com"


def deploy_public_dir_to_pages(
    public_dir: str | Path,
    workdir: str | Path,
    config: PagesDeployConfig,
) -> str | None:
    """
    Publish a built Hugo output directory to a Pages-friendly branch.

    This function:
    - creates/updates `config.branch` on `config.remote_url`
    - copies `public_dir` to a clean temporary git checkout under `workdir`
    - commits and pushes only when content changed
    """
    public_path = Path(public_dir)
    if not public_path.exists():
        raise RuntimeError(f"Public dir not found: {public_path}")

    root = Path(workdir)
    deploy_root = root / ".ghost-pages-deploy"
    if deploy_root.exists():
        shutil.rmtree(deploy_root)
    deploy_root.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")

    _git(deploy_root, ["init"], env=env)
    _git(deploy_root, ["config", "user.name", config.git_user_name], env=env)
    _git(deploy_root, ["config", "user.email", config.git_user_email], env=env)
    _git(deploy_root, ["remote", "add", "origin", config.remote_url], env=env)

    # Keep history when the branch exists; otherwise create it.
    fetched = _try_git(
        deploy_root, ["fetch", "--depth=1", "origin", config.branch], env=env
    )
    if fetched:
        _git(deploy_root, ["checkout", "-B", config.branch, "FETCH_HEAD"], env=env)
    else:
        _git(deploy_root, ["checkout", "-B", config.branch], env=env)

    _wipe_worktree(deploy_root)
    _copy_dir_contents(public_path, deploy_root)
    (deploy_root / ".nojekyll").write_text("", encoding="utf-8")
    if config.cname:
        (deploy_root / "CNAME").write_text(
            config.cname.strip() + "\n", encoding="utf-8"
        )

    _git(deploy_root, ["add", "-A"], env=env)
    has_changes = (
        _try_git(deploy_root, ["diff", "--cached", "--quiet"], env=env) is False
    )
    if not has_changes:
        return _git_output(deploy_root, ["rev-parse", "HEAD"], env=env).strip()

    msg = f"Deploy {datetime.now(timezone.utc).isoformat(timespec='seconds')}"
    _git(deploy_root, ["commit", "-m", msg], env=env)
    commit = _git_output(deploy_root, ["rev-parse", "HEAD"], env=env).strip()

    push_args = ["push", "origin", config.branch]
    if config.force:
        push_args.insert(1, "--force-with-lease")
    _git(deploy_root, push_args, env=env)
    return commit


def _git(cwd: Path, args: list[str], env: dict[str, str]) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, env=env)


def _try_git(cwd: Path, args: list[str], env: dict[str, str]) -> bool:
    proc = subprocess.run(["git", *args], cwd=str(cwd), env=env)
    return proc.returncode == 0


def _git_output(cwd: Path, args: list[str], env: dict[str, str]) -> str:
    return subprocess.check_output(["git", *args], cwd=str(cwd), env=env, text=True)


def _wipe_worktree(deploy_root: Path) -> None:
    for child in deploy_root.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _copy_dir_contents(src: Path, dst: Path) -> None:
    for child in src.iterdir():
        target = dst / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)


__all__ = ["PagesDeployConfig", "deploy_public_dir_to_pages"]
