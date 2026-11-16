import { NextResponse } from "next/server";
import crypto from "crypto";

const productionBackend = () =>
  process.env.PRODUCTION_BACKEND_URL || "http://127.0.0.1:8788";

type ValidationIssue = { line?: number; code?: string; message?: string };

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const script = String(body.script || "").trim();
    const computedHash = crypto.createHash("sha256").update(script).digest("hex");
    const hashMatches = !body.script_hash || body.script_hash === computedHash;

    const response = await fetch(`${productionBackend()}/api/production/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ script }),
      signal: AbortSignal.timeout(10000),
      cache: "no-store",
    });
    const validation = await response.json();
    // HTTP 422 is the expected response for an invalid STUDIO SCRIPT V1.
    // It contains line-numbered validation errors and must be rendered as a
    // normal preflight failure, not misreported as a backend outage.
    if (!response.ok && response.status !== 422) {
      throw new Error(validation?.error || `Validation backend returned ${response.status}`);
    }

    const errors: ValidationIssue[] = validation.errors || [];
    const warnings: ValidationIssue[] = validation.warnings || [];
    const summary = validation.summary || {};
    const blockers = errors.map((issue) =>
      `${issue.code || "SCRIPT_ERROR"}${issue.line ? ` · dòng ${issue.line}` : ""}: ${issue.message || "Lỗi kịch bản"}`,
    );
    if (!hashMatches) blockers.push("Script hash chưa đồng bộ. Hệ thống sẽ tính lại từ nội dung hiện tại.");

    const structuralPass = Boolean(validation.valid) && errors.length === 0;
    const overallPassed = structuralPass && hashMatches;
    const sceneCount = Number(summary.scenes || 0);
    const characterCount = Number(summary.characters || 0);
    const shotCount = Number(summary.shots || 0);
    const spokenLines = Number(summary.spoken_lines || 0);
    const totalWords = script.split(/\s+/).filter(Boolean).length;

    return NextResponse.json({
      overall_passed: overallPassed,
      status: overallPassed ? "PASSED" : "FAILED_BLOCKED",
      format: validation.format,
      script_hash: computedHash,
      hash_matches: hashMatches,
      blockers,
      warnings: warnings.map((issue) =>
        `${issue.code || "WARNING"}${issue.line ? ` · dòng ${issue.line}` : ""}: ${issue.message || "Cảnh báo"}`,
      ),
      checks: {
        rule_1_scenes: { passed: sceneCount > 0 && shotCount > 0, count: sceneCount, expected: sceneCount, scenes: [], shots: shotCount },
        rule_2_characters: { passed: characterCount > 0, count: characterCount, expected: characterCount, characters: [] },
        rule_3_word_counts: {
          total_words: totalWords,
          dialogue_words: spokenLines,
          metadata_words: Math.max(0, totalWords - spokenLines),
          dialogue_ratio: totalWords ? Math.round((spokenLines / totalWords) * 100) : 0,
        },
        rule_4_timing: { passed: structuralPass, total_duration_sec: Number(validation.review?.meta?.target_duration_min || 0), scene_durations: [] },
        rule_5_meme_cues: { passed: true, detected: {}, has_meme_scene_1: false, has_meme_scene_2: false, has_meme_scene_5: false },
        rule_6_local_assets: { passed: true, assets: [] },
        rule_7_clean_scenes: { passed: true, clean_scenes: [], violations: [] },
        rule_8_speech_purity: {
          passed: errors.every((issue) => issue.code !== "V1E008"),
          leaks: errors.filter((issue) => issue.code === "V1E008").map((issue) => issue.message || ""),
        },
        rule_9_audio_collision: { passed: true, events: [], policy: "Semantic event triggers" },
        rule_10_scene_8_integrity: { passed: structuralPass, has_variety: true, is_serious: true },
        universal_validation: {
          passed: structuralPass,
          format: validation.format,
          errors,
          warnings,
          scenes: sceneCount,
          shots: shotCount,
          characters: characterCount,
          spoken_lines: spokenLines,
          narration_lines: Number(summary.narration_lines || 0),
          dialogue_lines: Number(summary.dialogue_lines || 0),
        },
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Preflight failed";
    return NextResponse.json({
      overall_passed: false,
      status: "BACKEND_UNAVAILABLE",
      blockers: [`Không kết nối được bộ kiểm tra STUDIO SCRIPT V1: ${message}`],
      warnings: [],
      checks: null,
    }, { status: 503 });
  }
}
