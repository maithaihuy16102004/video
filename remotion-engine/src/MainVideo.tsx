import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  Audio,
  staticFile,
} from "remotion";

export interface Scene {
  title: string;
  spoken: string;
  keywords: string[];
}

export interface VideoProps {
  title: string;
  scenes: Scene[];
  theme: "gold" | "dark" | "emerald";
  audioPath?: string;
  bgmPath?: string;
}

export const MainVideo: React.FC<VideoProps> = ({
  title,
  scenes = [],
  theme = "gold",
  audioPath,
  bgmPath,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width, height } = useVideoConfig();

  // Bảng màu theo theme
  const themes = {
    gold: {
      bg1: "#1a1205",
      bg2: "#080502",
      accent: "#f59e0b",
      badgeBg: "rgba(245, 158, 11, 0.2)",
      text: "#fffbeb",
    },
    dark: {
      bg1: "#0b132b",
      bg2: "#02040a",
      accent: "#38bdf8",
      badgeBg: "rgba(56, 189, 248, 0.2)",
      text: "#f8fafc",
    },
    emerald: {
      bg1: "#06281b",
      bg2: "#010f0a",
      accent: "#10b981",
      badgeBg: "rgba(16, 185, 129, 0.2)",
      text: "#ecfdf5",
    },
  };

  const currentTheme = themes[theme] || themes.gold;

  // Tính toán scene hiện tại dựa trên tổng số frame
  const totalScenes = Math.max(1, scenes.length);
  const framesPerScene = Math.floor(durationInFrames / totalScenes);
  const currentSceneIndex = Math.min(
    totalScenes - 1,
    Math.floor(frame / framesPerScene)
  );
  const activeScene = scenes[currentSceneIndex] || {
    title: "",
    spoken: "",
    keywords: [],
  };

  const sceneLocalFrame = frame % framesPerScene;

  // Hiệu ứng Fade + Slide Up cho chữ
  const sceneOpacity = interpolate(
    sceneLocalFrame,
    [0, 15, framesPerScene - 15, framesPerScene],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const translateY = interpolate(
    sceneLocalFrame,
    [0, 15],
    [30, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // Hiệu ứng Zoom nhẹ cho background (Ken Burns Effect)
  const bgScale = interpolate(
    frame,
    [0, durationInFrames],
    [1, 1.15],
    { extrapolateRight: "clamp" }
  );

  // Thanh tiến trình chạy theo thời gian video
  const progressPercent = (frame / durationInFrames) * 100;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: currentTheme.bg2,
        color: currentTheme.text,
        fontFamily: "'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
        overflow: "hidden",
      }}
    >
      {/* 1. Nền Gradient Động đa tầng */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at 50% 35%, ${currentTheme.bg1} 0%, ${currentTheme.bg2} 100%)`,
          transform: `scale(${bgScale})`,
        }}
      />

      {/* Hiệu ứng hạt bụi phát sáng (Ambient Glow) */}
      <div
        style={{
          position: "absolute",
          top: "20%",
          left: "15%",
          width: 500,
          height: 500,
          borderRadius: "50%",
          background: currentTheme.accent,
          opacity: 0.12,
          filter: "blur(140px)",
        }}
      />

      {/* 2. Thanh Tiến Trình (Progress Bar) */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          height: 8,
          width: `${progressPercent}%`,
          background: `linear-gradient(90deg, ${currentTheme.accent}, #ffffff)`,
          zIndex: 100,
        }}
      />

      {/* 3. Header Tiêu Đề Cố Định */}
      <div
        style={{
          position: "absolute",
          top: 80,
          left: 60,
          right: 60,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          zIndex: 10,
        }}
      >
        <div
          style={{
            backgroundColor: currentTheme.badgeBg,
            border: `1px solid ${currentTheme.accent}`,
            color: currentTheme.accent,
            padding: "8px 24px",
            borderRadius: 30,
            fontSize: 26,
            fontWeight: 700,
            letterSpacing: 2,
            textTransform: "uppercase",
            marginBottom: 16,
          }}
        >
          {title}
        </div>
        <div
          style={{
            fontSize: 34,
            fontWeight: 800,
            color: "#ffffff",
            textAlign: "center",
            textShadow: "0 4px 16px rgba(0,0,0,0.8)",
          }}
        >
          Phần {currentSceneIndex + 1}/{totalScenes}: {activeScene.title}
        </div>
      </div>

      {/* 4. Trung Tâm Phân Cảnh (Animated Scene Content & Typography) */}
      <div
        style={{
          position: "absolute",
          top: "30%",
          left: 70,
          right: 70,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          opacity: sceneOpacity,
          transform: `translateY(${translateY}px)`,
          zIndex: 20,
        }}
      >
        {/* Hộp nội dung nổi bật */}
        <div
          style={{
            backgroundColor: "rgba(10, 15, 30, 0.65)",
            backdropFilter: "blur(20px)",
            borderRadius: 28,
            border: "1px solid rgba(255, 255, 255, 0.12)",
            padding: "50px 40px",
            boxShadow: "0 20px 50px rgba(0,0,0,0.6)",
            maxWidth: 940,
            textAlign: "center",
          }}
        >
          <p
            style={{
              fontSize: 44,
              lineHeight: 1.5,
              fontWeight: 600,
              color: "#ffffff",
              margin: 0,
              textShadow: "0 2px 8px rgba(0,0,0,0.8)",
            }}
          >
            "{activeScene.spoken}"
          </p>

          {/* Keywords Tag Badges */}
          {activeScene.keywords && activeScene.keywords.length > 0 && (
            <div
              style={{
                display: "flex",
                gap: 14,
                justifyContent: "center",
                flexWrap: "wrap",
                marginTop: 36,
              }}
            >
              {activeScene.keywords.map((kw, i) => (
                <span
                  key={i}
                  style={{
                    backgroundColor: "rgba(255, 255, 255, 0.08)",
                    border: `1px solid ${currentTheme.accent}`,
                    color: currentTheme.accent,
                    fontSize: 24,
                    fontWeight: 700,
                    padding: "6px 20px",
                    borderRadius: 16,
                  }}
                >
                  #{kw}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 5. Audio Tracks (Optional, Remotion CLI handles muxing via command or http) */}
    </AbsoluteFill>
  );
};
