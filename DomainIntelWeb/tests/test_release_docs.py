from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAIRS = (
    ("README.md", "README.zh-CN.md"),
    ("DomainIntelApp/README.md", "DomainIntelApp/README.zh-CN.md"),
    ("docs/onboarding-and-installation.md", "docs/onboarding-and-installation.zh-CN.md"),
    ("docs/release-readiness.md", "docs/release-readiness.zh-CN.md"),
    ("DESIGN.md", "DESIGN.zh-CN.md"),
)


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_install_guide_has_platform_commands_first_run_and_data_locations():
    english = _text("docs/onboarding-and-installation.md")
    chinese = _text("docs/onboarding-and-installation.zh-CN.md")
    for value in ("IntDog-<version>-windows-x64.exe", "IntDog-<version>-macos-arm64.dmg",
                  "chmod +x IntDog-<version>-linux-x64.AppImage", "%APPDATA%",
                  "~/Library/Application Support", "~/.config"):
        assert value in english
    for value in ("首次启动", "任务包", "系统凭据", "后台", "撤销", "卸载保留"):
        assert value in chinese
