# Test media cleanup rules

1. Test renders are disposable. After a test has passed and its report or required review artifact is saved, remove generated video, audio, frame caches, and renderer build caches.
2. Keep source code, source assets, JSON specifications, PNG storyboards/debug sheets, Markdown reports, and job metadata.
3. Before deletion, run `npm run cleanup:test-media:preview` from `remotion-engine` to review file count and recoverable space.
4. After validation, run `npm run cleanup:test-media` from `remotion-engine`.
5. Never point the cleanup script outside the fixed generated-data folders defined in `scripts/cleanup-test-media.ps1`.
6. A test that needs a retained video must copy it out of generated test folders and explicitly document why it is retained.
7. Studio draft and master videos are rendered only as temporary files, uploaded to Google Drive immediately after QA, and deleted locally whether upload succeeds or fails. The UI must expose the Drive URL, never a local `/videos/` URL.
