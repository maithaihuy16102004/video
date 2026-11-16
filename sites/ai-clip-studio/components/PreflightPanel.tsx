"use client";

import React, { useState, useEffect } from "react";
import {
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Play,
  Volume2,
  FileText,
  Clock,
  Sparkles,
  ChevronDown,
  ChevronUp
} from "lucide-react";

export interface PreflightReport {
  overall_passed: boolean;
  status: string;
  blockers: string[];
  hash_matches?: boolean;
  script_hash?: string;
  warnings?: string[];
  checks: {
    rule_1_scenes: { passed: boolean; count: number; expected: number; scenes: any[] };
    rule_2_characters: { passed: boolean; count: number; expected: number; characters: any[] };
    rule_3_word_counts: { total_words: number; dialogue_words: number; metadata_words: number; dialogue_ratio: number };
    rule_4_timing: { passed: boolean; total_duration_sec: number; scene_durations: any[] };
    rule_5_meme_cues: { passed: boolean; detected: Record<number, string>; has_meme_scene_1: boolean; has_meme_scene_2: boolean; has_meme_scene_5: boolean };
    rule_6_local_assets: { passed: boolean; assets: any[] };
    rule_7_clean_scenes: { passed: boolean; clean_scenes: number[]; violations: number[] };
    rule_8_speech_purity: { passed: boolean; leaks: string[] };
    rule_9_audio_collision: { passed: boolean; events: any[]; policy: string };
    rule_10_scene_8_integrity: { passed: boolean; has_variety: boolean; is_serious: boolean };
    rule_11_munich_1914_fidelity?: { passed: boolean; historical_period: string; found_forbidden_vienna: string[]; missing_required_munich: string[] };
  };
}

interface PreflightPanelProps {
  script: string;
  scriptHash?: string;
  onLoadCompliantScript: () => void;
  onAllowDraftRender?: () => void;
  onResult?: (passed: boolean) => void;
}

export const PreflightPanel: React.FC<PreflightPanelProps> = ({
  script,
  scriptHash,
  onLoadCompliantScript,
  onAllowDraftRender,
  onResult
}) => {
  const [report, setReport] = useState<PreflightReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(true);

  const runAudit = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/preflight", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ script, script_hash: scriptHash })
      });
      const data = await res.json();
      setReport(data);
      onResult?.(Boolean(data.overall_passed));
    } catch (err) {
      console.error("Preflight audit error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    runAudit();
  }, [script, scriptHash]);

  if (!report) return null;

  if (!report.checks) {
    return (
      <div className="rounded-[28px] border-[3px] border-[#172033] bg-white p-6 shadow-[8px_8px_0_#172033] mb-6">
        <div className="flex items-start gap-3 rounded-2xl border-2 border-[#e44d46] bg-[#fff1f0] p-4 text-[#e44d46]">
          <AlertTriangle className="mt-0.5 shrink-0" size={22} />
          <div className="min-w-0 flex-1">
            <div className="font-black">Không thể hoàn tất Preflight</div>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs font-bold">
              {(report.blockers?.length ? report.blockers : ["Backend kiểm tra chưa sẵn sàng."]).map((blocker, index) => (
                <li key={index}>{blocker}</li>
              ))}
            </ul>
            <button
              type="button"
              onClick={runAudit}
              disabled={loading}
              className="mt-3 rounded-xl border-2 border-[#172033] bg-[#ffd34e] px-4 py-2 text-xs font-black text-[#172033] shadow-[2px_2px_0_#172033] disabled:opacity-50"
            >
              {loading ? "Đang kết nối lại..." : "🔄 Chạy lại Preflight"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  const ch = report.checks;

  return (
    <div className="rounded-[28px] border-[3px] border-[#172033] bg-white p-6 shadow-[8px_8px_0_#172033] mb-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b-2 border-[#172033]/10 pb-4">
        <div className="flex items-center gap-3">
          <div
            className={`grid h-12 w-12 place-items-center rounded-2xl border-[3px] border-[#172033] text-white shadow-[3px_3px_0_#172033] ${
              report.overall_passed ? "bg-[#47bd75]" : "bg-[#e44d46]"
            }`}
          >
            {report.overall_passed ? <ShieldCheck size={28} /> : <ShieldAlert size={28} />}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-[#172033] px-3 py-0.5 text-xs font-black uppercase text-white">
                STUDIO SCRIPT V1 PREFLIGHT GATE
              </span>
              <span
                className={`rounded-full px-2.5 py-0.5 text-xs font-black uppercase ${
                  report.overall_passed ? "bg-[#47bd75] text-white" : "bg-[#e44d46] text-white"
                }`}
              >
                {report.overall_passed ? "PASSED" : "REJECTED / BLOCKED"}
              </span>
            </div>
            <h3 className="text-xl font-black mt-1">
              {report.overall_passed
                ? "Kịch bản hợp lệ · Cho phép xuất bản Audiovisual Draft"
                : "Phát hiện lỗi vi phạm tiêu chuẩn · MASTER RENDERING BỊ CHẶN TUYỆT ĐỐI"}
            </h3>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={runAudit}
            disabled={loading}
            className="rounded-xl border-2 border-[#172033] bg-[#ffd34e] px-4 py-2 text-xs font-black shadow-[2px_2px_0_#172033] hover:bg-white disabled:opacity-50"
          >
            {loading ? "Đang quét..." : "🔄 Chạy lại Preflight"}
          </button>
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="rounded-xl border-2 border-[#172033] bg-white p-2 text-xs font-black hover:bg-[#f3f0e8]"
          >
            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        </div>
      </div>

      {scriptHash && (
        <div className="mt-3 flex items-center gap-2 text-xs font-mono text-[#5b6477] bg-[#f8fafc] px-3 py-1.5 rounded-lg border border-[#e2e8f0]">
          <span className="font-bold text-[#172033]">Verified Script Hash (SHA-256):</span>
          <span className="truncate">{report.script_hash || scriptHash}</span>
          <span className={`ml-auto font-bold whitespace-nowrap ${report.hash_matches === false ? "text-red-600" : "text-emerald-600"}`}>
            {report.hash_matches === false ? "Đang đồng bộ lại" : "✓ Preflight Synced"}
          </span>
        </div>
      )}

      {/* Blocker Alert if Failed */}
      {!report.overall_passed && (
        <div className="mt-4 rounded-2xl border-2 border-[#e44d46] bg-[#fff1f0] p-4 text-[#e44d46]">
          <div className="flex items-start gap-2.5">
            <AlertTriangle className="mt-0.5 shrink-0" size={20} />
            <div>
              <div className="font-black text-sm uppercase tracking-wide">
                🛑 MASTER RENDERING IS CURRENTLY BLOCKED:
              </div>
              <ul className="mt-1 list-disc pl-5 text-xs font-bold space-y-1">
                {report.blockers.map((b, i) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
              <div className="mt-3 flex items-center gap-3">
                <span className="text-xs font-semibold text-[#172033]">
                  Sửa đúng các lỗi theo số dòng bên trên, sau đó chạy lại Preflight:
                </span>
                <button
                  type="button"
                  onClick={onLoadCompliantScript}
                  className="rounded-xl border-2 border-[#172033] bg-[#51d8e5] px-3 py-1.5 text-xs font-black text-[#172033] shadow-[2px_2px_0_#172033] hover:bg-white"
                >
                  ⚡ Nạp kịch bản mẫu
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 10 Criteria Breakdown */}
      {expanded && (
        <div className="mt-5 space-y-3">
          <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-5">
            {/* 1. Scenes */}
            <div className={`rounded-xl border-2 p-3 ${ch.rule_1_scenes.passed ? "border-[#47bd75] bg-[#f2faf5]" : "border-[#e44d46] bg-[#fff5f5]"}`}>
              <div className="flex items-center justify-between text-xs font-black">
                <span>1. Cảnh và shot hợp lệ</span>
                {ch.rule_1_scenes.passed ? <CheckCircle2 size={16} className="text-[#47bd75]" /> : <XCircle size={16} className="text-[#e44d46]" />}
              </div>
              <div className="mt-1 text-sm font-black">
                {ch.rule_1_scenes.count} cảnh
              </div>
              <div className="text-[11px] opacity-70">
                {ch.rule_1_scenes.passed ? "Parser nhận được cấu trúc cảnh/shot" : "Thiếu cảnh, shot hoặc tag bắt buộc"}
              </div>
            </div>

            {/* 2. Characters */}
            <div className={`rounded-xl border-2 p-3 ${ch.rule_2_characters.passed ? "border-[#47bd75] bg-[#f2faf5]" : "border-[#e44d46] bg-[#fff5f5]"}`}>
              <div className="flex items-center justify-between text-xs font-black">
                <span>2. Nhân vật khai báo</span>
                {ch.rule_2_characters.passed ? <CheckCircle2 size={16} className="text-[#47bd75]" /> : <XCircle size={16} className="text-[#e44d46]" />}
              </div>
              <div className="mt-1 text-sm font-black">
                {ch.rule_2_characters.count} nhân vật
              </div>
              <div className="text-[11px] opacity-70">
                {ch.rule_2_characters.passed ? "Có nhân vật hợp lệ" : "Chưa có nhân vật hợp lệ"}
              </div>
            </div>

            {/* 3. Word Count */}
            <div className="rounded-xl border-2 border-[#172033] bg-[#f9f8f4] p-3">
              <div className="flex items-center justify-between text-xs font-black">
                <span>3. Số Từ Thoại / Tổng</span>
                <FileText size={16} className="text-[#172033]" />
              </div>
              <div className="mt-1 text-sm font-black text-[#172033]">
                {ch.rule_3_word_counts.dialogue_words} / {ch.rule_3_word_counts.total_words} từ
              </div>
              <div className="text-[11px] opacity-70">
                Thoại: {ch.rule_3_word_counts.dialogue_ratio}% · Metadata: {ch.rule_3_word_counts.metadata_words} từ
              </div>
            </div>

            {/* 4. Durations */}
            <div className="rounded-xl border-2 border-[#172033] bg-[#f9f8f4] p-3">
              <div className="flex items-center justify-between text-xs font-black">
                <span>4. Thời Lượng Thực</span>
                <Clock size={16} className="text-[#172033]" />
              </div>
              <div className="mt-1 text-sm font-black text-[#172033]">
                {ch.rule_4_timing.total_duration_sec}s ước tính
              </div>
              <div className="text-[11px] opacity-70">
                Tính theo âm tiết thoại & action
              </div>
            </div>

            {/* 5. 3 Memes */}
            <div className={`rounded-xl border-2 p-3 ${ch.rule_5_meme_cues.passed ? "border-[#47bd75] bg-[#f2faf5]" : "border-[#e44d46] bg-[#fff5f5]"}`}>
              <div className="flex items-center justify-between text-xs font-black">
                <span>5. Meme là tùy chọn</span>
                {ch.rule_5_meme_cues.passed ? <CheckCircle2 size={16} className="text-[#47bd75]" /> : <XCircle size={16} className="text-[#e44d46]" />}
              </div>
              <div className="mt-1 text-sm font-black">
                Không bắt buộc
              </div>
              <div className="text-[11px] opacity-70">
                Không ép meme theo kịch bản khác
              </div>
            </div>
          </div>

          {/* Extended Checks */}
          <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-5 text-xs">
            {/* 6. Local Asset Resolution */}
            <div className="rounded-xl border border-[#172033]/20 bg-[#f9f8f4] p-2.5">
              <div className="flex items-center justify-between font-bold">
                <span>6. Tài sản âm thanh</span>
                <span className="text-[#47bd75] font-black">Theo kịch bản</span>
              </div>
              <div className="mt-1 text-[11px] opacity-75">
                SFX được kiểm tra theo event và asset thực tế.
              </div>
            </div>

            {/* 7. Clean Scenes */}
            <div className={`rounded-xl border p-2.5 ${ch.rule_7_clean_scenes.passed ? "border-[#47bd75]/40 bg-[#f2faf5]" : "border-[#e44d46]/40 bg-[#fff5f5]"}`}>
              <div className="flex items-center justify-between font-bold">
                <span>7. Chính sách meme</span>
                <span className={ch.rule_7_clean_scenes.passed ? "text-[#47bd75]" : "text-[#e44d46]"}>
                  {ch.rule_7_clean_scenes.passed ? "Hợp lệ" : "Vi phạm"}
                </span>
              </div>
              <div className="mt-1 text-[11px] opacity-75">
                Không áp quy tắc cảnh cố định của Episode khác.
              </div>
            </div>

            {/* 8. Speech Purity */}
            <div className={`rounded-xl border p-2.5 ${ch.rule_8_speech_purity.passed ? "border-[#47bd75]/40 bg-[#f2faf5]" : "border-[#e44d46]/40 bg-[#fff5f5]"}`}>
              <div className="flex items-center justify-between font-bold">
                <span>8. TTS Không Dính Tag</span>
                <span className="text-[#47bd75] font-black">100% PURE</span>
              </div>
              <div className="mt-1 text-[11px] opacity-75">
                Không lọt ACTION, CAMERA, SFX vào audio.
              </div>
            </div>

            {/* 9. Audio Collision Avoidance */}
            <div className="rounded-xl border border-[#172033]/20 bg-[#f9f8f4] p-2.5">
              <div className="flex items-center justify-between font-bold">
                <span>9. Timing Tránh Đè Lời</span>
                <span className="text-[#47bd75] font-black">DELAY +0.3s</span>
              </div>
              <div className="mt-1 text-[11px] opacity-75">
                Meme kích hoạt sau khi dứt thoại, gain -12dB.
              </div>
            </div>

            {/* 10. Scene 08 Integrity */}
            <div className={`rounded-xl border p-2.5 ${ch.rule_10_scene_8_integrity.passed ? "border-[#47bd75]/40 bg-[#f2faf5]" : "border-[#e44d46]/40 bg-[#fff5f5]"}`}>
              <div className="flex items-center justify-between font-bold">
                <span>10. Cấu trúc cuối</span>
                <span className={ch.rule_10_scene_8_integrity.passed ? "text-[#47bd75]" : "text-[#e44d46]"}>
                  {ch.rule_10_scene_8_integrity.passed ? "Đạt chuẩn" : "Chưa đạt"}
                </span>
              </div>
              <div className="mt-1 text-[11px] opacity-75">
                Kiểm tra cảnh cuối theo chính kịch bản hiện tại.
              </div>
            </div>

            {/* 11. Munich 1914 Historical Fidelity */}
            <div className={`col-span-full rounded-xl border p-2.5 ${!ch.rule_11_munich_1914_fidelity || ch.rule_11_munich_1914_fidelity.passed ? "border-[#47bd75]/40 bg-[#f2faf5]" : "border-[#e44d46]/40 bg-[#fff5f5]"}`}>
              <div className="flex items-center justify-between font-bold">
                <span>11. Độ Chính Xác Lịch Sử (Munich 1914 Fidelity)</span>
                <span className={!ch.rule_11_munich_1914_fidelity || ch.rule_11_munich_1914_fidelity.passed ? "text-[#47bd75]" : "text-[#e44d46]"}>
                  {!ch.rule_11_munich_1914_fidelity || ch.rule_11_munich_1914_fidelity.passed ? "Chuẩn Munich 1914" : "Lệch bối cảnh (Vienna)"}
                </span>
              </div>
              <div className="mt-1 text-[11px] opacity-75">
                Bảo đảm đúng bối cảnh Munich 1914 (Schleißheimer, Frauenkirche, Odeonsplatz). Tuyệt đối loại trừ Vienna.
              </div>
            </div>
          </div>

          {/* Action Bar */}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t-2 border-[#172033]/10 pt-4">
            <div className="text-xs font-semibold text-[#172033]/70">
              {report.overall_passed ? (
                <span className="text-[#2f9e5b] font-bold">
                  ✓ STUDIO SCRIPT V1 đã qua kiểm tra cấu trúc. Có thể tạo Audiovisual Draft để kiểm duyệt trực quan.
                </span>
              ) : (
                <span className="text-[#e44d46] font-bold">
                  ⚠️ Render Master bị khóa cho đến khi các lỗi STUDIO SCRIPT V1 được sửa.
                </span>
              )}
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={!report.overall_passed}
                onClick={onAllowDraftRender}
                className="flex items-center gap-2 rounded-xl border-2 border-[#172033] bg-[#ffd34e] px-4 py-2 text-xs font-black text-[#172033] shadow-[3px_3px_0_#172033] hover:bg-white disabled:opacity-40"
              >
                <Play size={14} fill="currentColor" /> Tạo 1 Bản Audiovisual Draft (Xem Trước)
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
