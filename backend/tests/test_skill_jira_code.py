"""jira-code 技能契约测试：锁定开发方案解析、feature 分支命名、单一进度评论与推送口径。"""
import ctypes
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.request import urlopen


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

PROJECT_ROOT = BACKEND_DIR.parent
SKILL_DIR = PROJECT_ROOT / "skills" / "jira-code"
SCRIPTS_DIR = SKILL_DIR / "scripts"
# 与 git-flow.mjs 的 CHECKOUT_MARKER_SUFFIX 保持一致：检出标记文件放在检出目录平级。
CHECKOUT_MARKER_SUFFIX = ".jira-code-checkout.json"
NODE = shutil.which("node")
GIT = shutil.which("git")

# Windows 进程查询/结束常量：沙箱里 tasklist/taskkill 会被拒绝，改用 Win32 API。
STILL_ACTIVE = 259
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001


def kill_pid(pid):
    """结束指定进程：POSIX 用 SIGTERM，Windows 用 TerminateProcess。"""
    value = int(pid)
    if os.name != "nt":
        os.kill(value, signal.SIGTERM)
        return
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, value)
    if not handle:
        return
    kernel32.TerminateProcess(handle, 1)
    kernel32.CloseHandle(handle)

# 方案文本样例：既覆盖「仓库 + 分支」的显式写法，也覆盖网页地址。
PLAN_READY = "\n".join(
    [
        "# 开发方案：购物车支持批量删除",
        "",
        "## 一、涉及仓库",
        "",
        "- 仓库：shop/cart-service",
        "- 目标分支：release/2.4",
        "",
        "## 二、实现要点",
        "",
        "1. 列表页新增批量删除入口",
        "",
    ]
)
PLAN_WITHOUT_REPO = "开发方案：把按钮改成蓝色。\n\n目标分支：release/2.4\n"
PLAN_WITHOUT_BRANCH = "开发方案：改动仓库：shop/cart-service，按现有代码风格实现。\n"


def run_node(script: str, *args, env=None, cwd=None, timeout=120):
    """用 node 执行技能脚本，返回带 returncode/stdout/stderr 的结果。"""
    command = [NODE, str(SCRIPTS_DIR / script), *[str(item) for item in args]]
    return subprocess.run(
        command,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(cwd or PROJECT_ROOT),
        timeout=timeout,
        check=False,
    )


def run_git(*args, cwd=None):
    """执行 git 命令，失败时直接抛出，用于准备测试仓库。"""
    return subprocess.run(
        [GIT, *[str(item) for item in args]],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd) if cwd else None,
        check=True,
    )


class SkillPackagingTests(unittest.TestCase):
    """技能目录结构、注册信息与文档硬约束。"""

    def test_required_files_are_shipped(self):
        """技能需要随仓库分发：入口、脚本、参考资料与运行配置都要在。"""
        expected = [
            SKILL_DIR / "SKILL.md",
            SKILL_DIR / "runtime.json",
            SKILL_DIR / "agents" / "openai.yaml",
            SCRIPTS_DIR / "jira.mjs",
            SCRIPTS_DIR / "jira-cli.mjs",
            SCRIPTS_DIR / "plan.mjs",
            SCRIPTS_DIR / "git-flow.mjs",
            SCRIPTS_DIR / "progress.mjs",
            SCRIPTS_DIR / "extract.py",
            SKILL_DIR / "references" / "jira-api.md",
            SKILL_DIR / "references" / "gitlab-api.md",
            SKILL_DIR / "references" / "plan-format.md",
        ]
        for path in expected:
            self.assertTrue(path.is_file(), f"缺少技能文件：{path}")

    def test_skill_is_registered_with_long_timeout(self):
        """技能要能被注册表发现，且给出足够长的超时时间（写代码远慢于读单子）。"""
        from app.skillrun.registry import load_skill

        skill = load_skill(SKILL_DIR, "jira-code")

        self.assertEqual(skill.skill_id, "jira-code")
        self.assertTrue(skill.description)
        self.assertGreaterEqual(skill.timeout_seconds, 3600)
        self.assertIn("jira_url", skill.required_inputs)
        self.assertIn("feature/<KEY>", skill.prompt_template)

    def test_skill_documents_hard_rules(self):
        """SKILL.md 必须写明分支命名、单条评论、不等确认与允许中断的条件。"""
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("feature/<KEY>", text)
        self.assertIn("不要停下来等人工确认", text)
        self.assertIn("每 5 分钟", text)
        self.assertIn("一条需求单只允许一条进度评论", text)
        self.assertIn("不改单子状态", text)
        self.assertIn("不在工作区留代码副本", text)
        self.assertIn("cleanup", text)
        self.assertIn("信息不足：评论 + 中断", text)

    def test_cli_exposes_no_state_changing_commands(self):
        """命令行入口只提供读单子与写评论，不能出现流转/门禁字段这类改单子的能力。"""
        source = (SCRIPTS_DIR / "jira-cli.mjs").read_text(encoding="utf-8")

        self.assertIn('case "comment-update"', source)
        self.assertIn('case "comments"', source)
        for forbidden in ("gate-set", "gate-get", "transition", "flow-owner"):
            self.assertNotIn(f'case "{forbidden}"', source)

    def test_references_cover_credentials_and_plan_rules(self):
        """参考资料要写清凭据来源与方案识别规则，避免执行时临时发挥。"""
        gitlab = (SKILL_DIR / "references" / "gitlab-api.md").read_text(encoding="utf-8")
        plan = (SKILL_DIR / "references" / "plan-format.md").read_text(encoding="utf-8")

        self.assertIn("GITLAB_PRIVATE_TOKEN", gitlab)
        self.assertIn("GIT_BASE_URL", gitlab)
        self.assertIn("不写进 `.git/config`", gitlab)
        self.assertIn("git-flow.mjs push", gitlab)
        self.assertIn("git-flow.mjs cleanup", gitlab)
        self.assertIn("unpushed-commits", gitlab)
        self.assertIn("pairs", plan)
        self.assertIn("repo-not-found", plan)


@unittest.skipUnless(NODE, "未安装 node，跳过技能脚本测试")
class PlanExtractionTests(unittest.TestCase):
    """plan.mjs：挑方案文件 + 提取仓库/分支候选。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name: str, text: str) -> Path:
        """在临时目录里落一个文件并返回路径。"""
        target = self.root / name
        target.write_text(text, encoding="utf-8")
        return target

    def test_candidates_extract_repo_branch_and_pair(self):
        """显式写法「仓库：/目标分支：」要配成一对，网页地址要规范化成 .git 仓库地址。"""
        plan = self.write(
            "plan.md",
            PLAN_READY + "\n相关系统：https://code.in.wezhuiyi.com/shop/api-gateway/-/blob/develop/README.md\n",
        )

        result = run_node("plan.mjs", "candidates", plan)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["pairs"][0]["branch"], "release/2.4")
        self.assertEqual(payload["pairs"][0]["repo"], "shop/cart-service")
        urls = [item.get("url") for item in payload["repos"]]
        self.assertIn("https://code.in.wezhuiyi.com/shop/api-gateway.git", urls)
        self.assertIn("release/2.4", [item["name"] for item in payload["branches"]])

    def test_candidates_abort_without_repo_or_branch(self):
        """方案缺仓库或缺分支时必须退出码 1，让技能能确定性中断流程。"""
        without_repo = self.write("no-repo.md", PLAN_WITHOUT_REPO)
        without_branch = self.write("no-branch.md", PLAN_WITHOUT_BRANCH)

        missing_repo = run_node("plan.mjs", "candidates", without_repo)
        self.assertEqual(missing_repo.returncode, 1)
        self.assertEqual(json.loads(missing_repo.stdout)["reason"], "repo-not-found")
        self.assertIn("[开发方案解析失败]", missing_repo.stderr)

        missing_branch = run_node("plan.mjs", "candidates", without_branch)
        self.assertEqual(missing_branch.returncode, 1)
        self.assertEqual(json.loads(missing_branch.stdout)["reason"], "branch-not-found")

    def test_find_picks_dev_plan_attachment(self):
        """附件目录里有多个文档时优先选「开发方案」，没有候选时给出目录内容。"""
        self.write("需求文档.md", "# 需求\n")
        self.write("开发方案-v2.md", "# 开发方案\n")
        self.write("截图.png", "not-a-real-image")

        picked = run_node("plan.mjs", "find", self.root)

        self.assertEqual(picked.returncode, 0, picked.stderr)
        self.assertEqual(Path(json.loads(picked.stdout)["name"]).name, "开发方案-v2.md")

        empty = self.root / "empty"
        empty.mkdir()
        missing = run_node("plan.mjs", "find", empty)
        self.assertEqual(missing.returncode, 1)
        self.assertEqual(json.loads(missing.stdout)["reason"], "attachment-not-found")


@unittest.skipUnless(NODE and GIT, "未安装 node/git，跳过 Git 流程测试")
class GitFlowTests(unittest.TestCase):
    """git-flow.mjs：分支命名、提交推送、失败原因与令牌不外泄。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        cls.bare = cls.root / "origin.git"
        seed = cls.root / "seed"
        run_git("init", "--bare", "--quiet", cls.bare)
        run_git("init", "--quiet", seed)
        (seed / "README.md").write_text("# cart service\n", encoding="utf-8")
        run_git("-C", seed, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
        run_git("-C", seed, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "--quiet", "-m", "init")
        run_git("-C", seed, "branch", "-M", "release/2.4")
        run_git("-C", seed, "remote", "add", "origin", cls.bare)
        run_git("-C", seed, "push", "--quiet", "origin", "release/2.4")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def new_checkout(self, name: str) -> Path:
        """为单个用例准备独立的检出目录，避免用例之间互相影响。"""
        return self.root / name

    def test_prepare_creates_feature_branch_named_by_key(self):
        """分支名必须是 feature/<KEY>，且内容来自方案里的基线分支。"""
        checkout = self.new_checkout("checkout-ok")

        result = run_node(
            "git-flow.mjs", "prepare",
            "--repo", self.bare, "--base", "release/2.4", "--key", "ZYSQ-95", "--dir", checkout,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["feature"], "feature/ZYSQ-95")
        self.assertEqual(payload["base"], "release/2.4")
        self.assertEqual(payload["snapshot"]["branch"], "feature/ZYSQ-95")
        self.assertTrue((checkout / "README.md").is_file(), "基线分支的文件没有检出")

    def test_commit_and_push_land_on_remote_feature_branch(self):
        """提交后推送：远端要出现 feature/<KEY>，且内容包含新写的文件。"""
        checkout = self.new_checkout("checkout-push")
        prepare = run_node(
            "git-flow.mjs", "prepare",
            "--repo", self.bare, "--base", "release/2.4", "--key", "ZYSQ-95", "--dir", checkout,
        )
        self.assertEqual(prepare.returncode, 0, prepare.stderr)
        (checkout / "src").mkdir()
        (checkout / "src" / "Cart.java").write_text("class Cart {}\n", encoding="utf-8")

        commit = run_node(
            "git-flow.mjs", "commit", "--dir", checkout,
            "--message", "feat(ZYSQ-95): 支持批量删除",
        )
        self.assertEqual(commit.returncode, 0, commit.stderr)
        committed = json.loads(commit.stdout)
        self.assertTrue(committed["committed"])
        self.assertIn("src/Cart.java", committed["files"])

        push = run_node("git-flow.mjs", "push", "--dir", checkout)
        self.assertEqual(push.returncode, 0, push.stderr)
        self.assertTrue(json.loads(push.stdout)["pushed"])

        branches = run_git("-C", self.bare, "branch", "--list").stdout
        self.assertIn("feature/ZYSQ-95", branches)
        files = run_git("-C", self.bare, "ls-tree", "--name-only", "-r", "feature/ZYSQ-95").stdout
        self.assertIn("src/Cart.java", files)

    def test_missing_base_branch_lists_remote_branches(self):
        """基线分支不存在时要报 base-branch-not-found 并给出远端现有分支。"""
        checkout = self.new_checkout("checkout-missing-base")

        result = run_node(
            "git-flow.mjs", "prepare",
            "--repo", self.bare, "--base", "release/9.9", "--key", "ZYSQ-95", "--dir", checkout,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("base-branch-not-found", result.stderr)
        self.assertIn("release/2.4", result.stderr)

    def test_token_never_reaches_output_or_repo_config(self):
        """令牌只做临时参数：输出里脱敏，检出目录的 .git/config 里不留凭据。"""
        secret = "glpat-super-secret-token"
        checkout = self.new_checkout("checkout-token")
        env = dict(os.environ, GITLAB_PRIVATE_TOKEN=secret)

        # 连不上的地址：必然失败，正好用来确认报错信息与仓库配置都不含令牌。
        result = run_node(
            "git-flow.mjs", "prepare",
            "--repo", "https://127.0.0.1:1/group/repo.git", "--base", "develop",
            "--key", "ZYSQ-95", "--dir", checkout, env=env,
        )
        creds = run_node("git-flow.mjs", "creds", env=env)

        self.assertEqual(result.returncode, 1)
        self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertNotIn(secret, creds.stdout + creds.stderr)
        self.assertIn("private-token", creds.stdout)
        config = (checkout / ".git" / "config").read_text(encoding="utf-8")
        self.assertNotIn(secret, config)
        self.assertFalse(
            any("://" in line and "@" in line for line in config.splitlines() if line.strip().startswith("url")),
            f"origin 里出现了带凭据的地址：{config}",
        )

    def test_redact_masks_credentials_in_urls(self):
        """脱敏函数要把 URL 里的账号密码替换掉，前缀保持不变。"""
        script = SCRIPTS_DIR / "git-flow.mjs"
        code = (
            f"import({script.as_uri()!r}).then((m) => "
            "process.stdout.write(m.redact('fatal: unable to access https://oauth2:tok123@host/g/r.git', ['tok123'])) )"
        )

        result = subprocess.run(
            [NODE, "-e", code], capture_output=True, encoding="utf-8", errors="replace",
            cwd=str(PROJECT_ROOT), check=False, timeout=60,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("https://***@host/g/r.git", result.stdout)
        self.assertNotIn("tok123", result.stdout)

    def test_cleanup_removes_checkout_after_push(self):
        """推送成功后 cleanup 删掉本地检出与标记，远端 feature 分支不受影响。"""
        checkout = self.new_checkout("checkout-cleanup-ok")
        marker = checkout.with_name(f"{checkout.name}{CHECKOUT_MARKER_SUFFIX}")
        prepare = run_node(
            "git-flow.mjs", "prepare",
            "--repo", self.bare, "--base", "release/2.4", "--key", "ZYSQ-101", "--dir", checkout,
        )
        self.assertEqual(prepare.returncode, 0, prepare.stderr)
        self.assertTrue(marker.is_file(), "prepare 没有写下检出标记")

        (checkout / "src").mkdir()
        (checkout / "src" / "Cart.java").write_text("class Cart {}\n", encoding="utf-8")
        commit = run_node("git-flow.mjs", "commit", "--dir", checkout, "--message", "feat(ZYSQ-101): 支持批量删除")
        self.assertEqual(commit.returncode, 0, commit.stderr)
        push = run_node("git-flow.mjs", "push", "--dir", checkout)
        self.assertEqual(push.returncode, 0, push.stderr)

        cleaned = run_node("git-flow.mjs", "cleanup", "--dir", checkout, "--key", "ZYSQ-101", "--verify-remote")
        self.assertEqual(cleaned.returncode, 0, cleaned.stderr)
        self.assertTrue(json.loads(cleaned.stdout)["removed"])
        self.assertFalse(checkout.exists(), "推送成功后应该删掉本地检出目录")
        self.assertFalse(marker.exists(), "检出标记也要一并删除")
        self.assertIn("feature/ZYSQ-101", run_git("-C", self.bare, "branch", "--list").stdout)

    def test_cleanup_refuses_checkout_with_unpushed_commits(self):
        """还有提交没推上去时拒绝删除，避免把没进远端的代码丢掉。"""
        checkout = self.new_checkout("checkout-cleanup-unpushed")
        prepare = run_node(
            "git-flow.mjs", "prepare",
            "--repo", self.bare, "--base", "release/2.4", "--key", "ZYSQ-102", "--dir", checkout,
        )
        self.assertEqual(prepare.returncode, 0, prepare.stderr)
        (checkout / "a.txt").write_text("x\n", encoding="utf-8")
        commit = run_node("git-flow.mjs", "commit", "--dir", checkout, "--message", "feat(ZYSQ-102): 未推送的改动")
        self.assertEqual(commit.returncode, 0, commit.stderr)

        result = run_node("git-flow.mjs", "cleanup", "--dir", checkout)
        self.assertEqual(result.returncode, 1)
        self.assertIn("unpushed-commits", result.stderr)
        self.assertTrue(checkout.exists(), "拒绝删除时目录必须保留")

        forced = run_node("git-flow.mjs", "cleanup", "--dir", checkout, "--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertFalse(checkout.exists(), "--force 时允许丢弃未推送的检出")

    def test_cleanup_refuses_checkout_without_marker(self):
        """没有本技能标记的目录一律拒绝删除。"""
        plain = self.new_checkout("checkout-not-managed")
        plain.mkdir()
        (plain / "keep.txt").write_text("keep\n", encoding="utf-8")

        result = run_node("git-flow.mjs", "cleanup", "--dir", plain)

        self.assertEqual(result.returncode, 1)
        self.assertIn("not-managed-checkout", result.stderr)
        self.assertTrue((plain / "keep.txt").is_file(), "非本技能的目录不能被删掉")

    def test_cleanup_refuses_checkout_with_mismatched_key(self):
        """--key 与标记不一致时拒绝，避免误删别的单子的检出。"""
        checkout = self.new_checkout("checkout-cleanup-key")
        prepare = run_node(
            "git-flow.mjs", "prepare",
            "--repo", self.bare, "--base", "release/2.4", "--key", "ZYSQ-103", "--dir", checkout,
        )
        self.assertEqual(prepare.returncode, 0, prepare.stderr)

        result = run_node("git-flow.mjs", "cleanup", "--dir", checkout, "--key", "ZYSQ-777")

        self.assertEqual(result.returncode, 1)
        self.assertIn("key-mismatch", result.stderr)
        self.assertTrue(checkout.exists())

    def test_cleanup_keeps_checkout_when_remote_branch_missing(self):
        """--verify-remote：远端没有该 feature 分支时保留本地目录，说明代码没推上去。"""
        checkout = self.new_checkout("checkout-cleanup-noremote")
        marker = checkout.with_name(f"{checkout.name}{CHECKOUT_MARKER_SUFFIX}")
        prepare = run_node(
            "git-flow.mjs", "prepare",
            "--repo", self.bare, "--base", "release/2.4", "--key", "ZYSQ-104", "--dir", checkout,
        )
        self.assertEqual(prepare.returncode, 0, prepare.stderr)
        # 标记里写一个远端不存在的分支：模拟「代码没推成功」。
        data = json.loads(marker.read_text(encoding="utf-8"))
        data["feature"] = "feature/ZYSQ-104"
        marker.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        result = run_node("git-flow.mjs", "cleanup", "--dir", checkout, "--verify-remote")

        self.assertEqual(result.returncode, 1)
        self.assertIn("remote-branch-missing", result.stderr)
        self.assertTrue(checkout.exists(), "远端没有分支时必须保留本地目录")


@unittest.skipUnless(NODE, "未安装 node，跳过进度评论测试")
class ProgressCommentTests(unittest.TestCase):
    """progress.mjs：一条单子只允许一条进度评论，心跳与终态都写进同一条。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.mock = subprocess.Popen(
            [NODE, str(SCRIPTS_DIR / "mock-jira.mjs"), "--json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            cwd=str(SKILL_DIR),
        )
        self.addCleanup(self._stop_mock)
        line = self.mock.stdout.readline()
        if not line:
            # 先结束进程再读 stderr：进程存活时 read() 会一直阻塞，导致用例卡死。
            self._stop_mock()
            self.fail(f"mock JIRA 未启动：{self.mock.stderr.read()}")
        info = json.loads(line)
        self.base_url = info["baseUrl"]
        self.env = dict(os.environ, JIRA_BASE_URL=self.base_url, JIRA_TOKEN=info["token"])

    def _stop_mock(self):
        """结束 mock 进程并回收管道，避免测试进程残留。"""
        if self.mock.poll() is None:
            self.mock.kill()
            self.mock.wait(timeout=10)
        for stream in (self.mock.stdout, self.mock.stderr):
            try:
                stream.close()
            except Exception:  # noqa: BLE001 - 管道可能已被回收
                pass

    def mock_comments(self, key: str = "SHOP-201"):
        """读取 mock 里该单当前的评论列表。"""
        with urlopen(f"{self.base_url}/__mock/state", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload["comments"].get(key, [])

    def state_file(self, name: str = "progress.json") -> Path:
        """为用例准备状态文件路径，并登记心跳清理。"""
        target = self.root / name
        self.addCleanup(self._kill_daemon, target)
        return target

    def _kill_daemon(self, state_path: Path):
        """用例结束时按状态文件里的 pid 结束心跳进程。"""
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - 状态文件可能不存在
            return
        pid = state.get("daemonPid")
        if not pid:
            return
        try:
            kill_pid(pid)
        except Exception:  # noqa: BLE001 - 进程可能已退出
            pass

    def pid_alive(self, pid) -> bool:
        """跨平台判断进程是否还在：POSIX 用信号 0，Windows 用 OpenProcess（不依赖被沙箱限制的 tasklist）。"""
        if not pid:
            return False
        if os.name == "nt":
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not handle:
                return False
            code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            kernel32.CloseHandle(handle)
            return bool(ok) and code.value == STILL_ACTIVE
        try:
            os.kill(int(pid), 0)
            return True
        except OSError:
            return False

    def test_start_creates_single_comment_and_update_reuses_it(self):
        """start 建一条评论，update 只更新这一条，绝不新增第二条。"""
        state = self.state_file()
        started = run_node(
            "progress.mjs", "start", "--issue", "SHOP-201", "--state", state,
            "--stage", "已读取开发方案", "--summary", "购物车批量删除",
            "--branch", "feature/SHOP-201", "--interval", "60", env=self.env,
        )
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertTrue(json.loads(started.stdout)["ok"])
        first = self.mock_comments()
        self.assertEqual(len(first), 1)
        self.assertIn("jira-code:progress:SHOP-201", first[0]["body"])
        self.assertIn("进行中", first[0]["body"])

        updated = run_node(
            "progress.mjs", "update", "--state", state,
            "--stage", "编写代码", "--step", "已完成批量删除接口", env=self.env,
        )
        self.assertEqual(updated.returncode, 0, updated.stderr)

        second = self.mock_comments()
        self.assertEqual(len(second), 1, "update 不应该新增评论")
        self.assertEqual(second[0]["id"], first[0]["id"])
        self.assertIn("编写代码", second[0]["body"])
        self.assertIn("已完成批量删除接口", second[0]["body"])
        self.assertGreaterEqual(second[0]["updates"], 1)

    def test_heartbeat_refreshes_the_same_comment(self):
        """心跳按间隔自动刷新同一条评论：既不新增评论，内容也真的会更新。"""
        state = self.state_file("heartbeat.json")
        started = run_node(
            "progress.mjs", "start", "--issue", "SHOP-201", "--state", state,
            "--stage", "编写代码", "--interval", "1", env=self.env,
        )
        self.assertEqual(started.returncode, 0, started.stderr)
        pid = json.loads(started.stdout)["daemonPid"]
        self.assertTrue(self.pid_alive(pid), "心跳进程没有起来")

        time.sleep(3.5)

        comments = self.mock_comments()
        self.assertEqual(len(comments), 1)
        self.assertGreaterEqual(comments[0]["updates"], 2, "心跳没有按间隔刷新评论")
        self.assertGreaterEqual(json.loads(state.read_text(encoding="utf-8"))["publishCount"], 2)

    def test_finish_marks_done_and_stops_daemon(self):
        """finish 写最终状态、保留同一条评论，并停掉心跳进程。"""
        state = self.state_file("finish.json")
        started = run_node(
            "progress.mjs", "start", "--issue", "SHOP-201", "--state", state,
            "--stage", "编写代码", "--interval", "1", env=self.env,
        )
        pid = json.loads(started.stdout)["daemonPid"]

        finished = run_node(
            "progress.mjs", "finish", "--state", state,
            "--message", "已推送 feature/SHOP-201（shop/cart-service）", env=self.env,
        )

        self.assertEqual(finished.returncode, 0, finished.stderr)
        payload = json.loads(finished.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "done")
        comments = self.mock_comments()
        self.assertEqual(len(comments), 1)
        self.assertIn("已完成", comments[0]["body"])
        self.assertIn("feature/SHOP-201", comments[0]["body"])
        saved = json.loads(state.read_text(encoding="utf-8"))
        self.assertIsNone(saved["daemonPid"])
        time.sleep(0.5)
        self.assertFalse(self.pid_alive(pid), "finish 之后心跳进程仍在运行")

    def test_fail_records_reason_in_the_same_comment(self):
        """中断/异常只更新同一条评论：状态改为已中断并带上原因。"""
        state = self.state_file("fail.json")
        run_node(
            "progress.mjs", "start", "--issue", "SHOP-202", "--state", state,
            "--stage", "解析开发方案", "--interval", "60", env=self.env,
        )

        failed = run_node(
            "progress.mjs", "fail", "--state", state,
            "--message", "方案里没有仓库与分支信息，已中断：请补充后重新触发", env=self.env,
        )

        self.assertEqual(failed.returncode, 0, failed.stderr)
        comments = self.mock_comments("SHOP-202")
        self.assertEqual(len(comments), 1)
        self.assertIn("已中断", comments[0]["body"])
        self.assertIn("请补充后重新触发", comments[0]["body"])

    def test_rerun_reuses_existing_progress_comment(self):
        """重跑同一张单（状态文件重建）时按标记复用已有评论，不会刷出第二条。"""
        first_state = self.state_file("run1.json")
        run_node(
            "progress.mjs", "start", "--issue", "SHOP-201", "--state", first_state,
            "--stage", "第一次执行", "--interval", "60", env=self.env,
        )
        first = self.mock_comments()
        self.assertEqual(len(first), 1)

        second_state = self.state_file("run2.json")
        restarted = run_node(
            "progress.mjs", "start", "--issue", "SHOP-201", "--state", second_state,
            "--stage", "第二次执行", "--interval", "60", env=self.env,
        )

        self.assertEqual(restarted.returncode, 0, restarted.stderr)
        comments = self.mock_comments()
        self.assertEqual(len(comments), 1, "重跑后出现了第二条进度评论")
        self.assertEqual(comments[0]["id"], first[0]["id"])
        self.assertIn("第二次执行", comments[0]["body"])
        run_node("progress.mjs", "stop", "--state", second_state, env=self.env)


if __name__ == "__main__":
    unittest.main()
