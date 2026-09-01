from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAIRS = (
    ("README.md", "README.zh-CN.md"),
    ("DomainIntelApp/README.md", "DomainIntelApp/README.zh-CN.md"),
    ("docs/onboarding-and-installation.md", "docs/onboarding-and-installation.zh-CN.md"),
    ("docs/release-readiness.md", "docs/release-readiness.zh-CN.md"),
    ("IMPLEMENTATION_STATUS.md", "IMPLEMENTATION_STATUS.zh-CN.md"),
    ("DESIGN.md", "DESIGN.zh-CN.md"),
)


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_bilingual_user_docs_cover_the_same_release_contract():
    concepts = (
        ("Windows", "Windows"), ("macOS", "macOS"), ("Linux", "Linux"),
        ("no-model", "无模型"), ("Agent", "Agent"), ("API", "API"),
        ("background", "后台"), ("revoke", "撤销"), ("data", "数据"),
        ("uninstall", "卸载"), ("Beta", "Beta"),
    )
    for english_path, chinese_path in PAIRS[:3]:
        english, chinese = _text(english_path), _text(chinese_path)
        for english_term, chinese_term in concepts:
            assert english_term.casefold() in english.casefold(), (english_path, english_term)
            assert chinese_term.casefold() in chinese.casefold(), (chinese_path, chinese_term)


def test_install_guide_has_platform_commands_first_run_and_data_locations():
    english = _text("docs/onboarding-and-installation.md")
    chinese = _text("docs/onboarding-and-installation.zh-CN.md")
    for value in ("IntDog-<version>-windows-x64.exe", "IntDog-<version>-macos-arm64.dmg",
                  "chmod +x IntDog-<version>-linux-x64.AppImage", "%APPDATA%",
                  "~/Library/Application Support", "~/.config"):
        assert value in english
    for value in ("首次启动", "任务包", "系统凭据", "后台", "撤销", "卸载保留"):
        assert value in chinese


def test_status_and_design_do_not_claim_external_native_gates_passed():
    for relative in ("IMPLEMENTATION_STATUS.md", "IMPLEMENTATION_STATUS.zh-CN.md",
                     "docs/release-readiness.md", "docs/release-readiness.zh-CN.md"):
        text = _text(relative)
        assert "NOM-01" in text
        assert ("external gap" in text.casefold() or "外部缺口" in text)
    assert "SP4" in _text("IMPLEMENTATION_STATUS.md")
    assert "SP5 A" in _text("IMPLEMENTATION_STATUS.md")
