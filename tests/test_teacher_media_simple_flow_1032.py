from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ai_media_modes_share_one_simple_teacher_flow_and_return_handoff():
    source = ROOT.joinpath("static", "teacher-ai-media-studio-1018.js").read_text(encoding="utf-8")
    for marker in (
        "teacher-media-simple-flow-1032",
        "1 丟入資料",
        "2 需求（選填）",
        "3 試產出／AI 修正",
        "4 完成帶回教材",
        "請 AI 再修一次",
        "製作完成，帶回教材",
        "teacher-media-authoring-finished",
        "teacher.mediaAuthoring.lastResult.v1",
        "cancelable: true",
        "TeacherWorkspace1014?.openCourse",
        "finishAndReturn",
    ):
        assert marker in source

    # PowerPoint and narration can regenerate from the same source with a new
    # teacher instruction. Video sends the revision back through the prepared
    # source / PowerPoint lane instead of pretending FFmpeg can rewrite content.
    for marker in (
        "teacher-ai-material-focus-1014",
        "teacher-ai-material-generate-1014",
        "teacher-script-focus-1014",
        "teacher-script-generate-1014",
        "openVideoSourceWorkspace",
        "TeacherPresentationChoicesCache1026",
        "paintMaterialOptions",
    ):
        assert marker in source


def test_optional_requirements_are_progressively_disclosed_in_all_ai_modes():
    powerpoint = ROOT.joinpath("static", "teacher-ai-material-1014.js").read_text(encoding="utf-8")
    narration = ROOT.joinpath("static", "teacher-media-script-1014.js").read_text(encoding="utf-8")
    video = ROOT.joinpath("static", "teacher-ai-video-1015.js").read_text(encoding="utf-8")

    assert "teacher-ai-material-requirements-1032" in powerpoint
    assert "需求（選填）｜語氣、篇幅、特別重點" in powerpoint
    assert "✨ 試產出 PowerPoint 大綱" in powerpoint

    assert "teacher-script-requirements-1032" in narration
    assert "需求（選填）｜語氣、篇幅、特別重點" in narration
    assert "✨ 試產出講稿" in narration

    assert "teacher-ai-video-requirements-1032" in video
    assert "需求（選填）｜旁白聲音" in video
    assert "✨ 試產出影片" in video
    assert "最終片長依核准投影片與旁白而定" in video
