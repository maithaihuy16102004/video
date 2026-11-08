const script = `
**Chính trị.**
Và chuyện đó bắt đầu...
trong một căn phòng đầy những người mà ban đầu tôi được cử tới để theo dõi.
**TẬP 2: TỪ NGƯỜI LÍNH THẤT BẠI ĐẾN KẺ KÍCH ĐỘNG CHÍNH TRỊ**
- Phong cách: Ukiyo-e Stickman
- Lịch sử: Đức 1919
`;
const IGNORED_NAME_PREFIXES = [
  'tập', 'cảnh', 'hồi', 'phần', 'bước', 'lưu ý', 'chú ý', 'lịch sử', 'thời gian',
  'năm', 'hết', 'ghi chú', 'hướng dẫn', 'nhân vật', 'bối cảnh', 'phong cách',
  'ngôi kể', 'dark comedy', 'ước tính', 'bài học', 'nội dung', 'yêu cầu',
  'trạm', 'con phố', 'cây cầu', 'ngôi nhà', 'đây là', 'hãy', 'không', 'đoạn',
  'chính trị', 'thời', 'lưu', 'đây', 'ngôi', 'dark', 'hã', 'hư', 'hú', 'iế', 'hế', 'bướ',
  'scene', 'act', 'chapter', 'note', 'prompt', 'test', 'haru (kể', 'haru kể'
];

const blocks = [];
for (const raw of script.split(/\n+/)) {
  const line = raw.trim().replace(/^[-*#_~`“”•\d.]+|[*#_~`“”]+$/g, '').trim();
  const m = line.match(/^([A-ZÀ-ỸĐ0-9][A-ZÀ-ỸĐ0-9 ._\-()]{1,42}):\s*(.*)$/i);
  if (m) {
    const rawSpeaker = m[1].trim();
    const cleanSpeaker = rawSpeaker.replace(/\(.*?\)/g, '').trim();
    const lowerClean = cleanSpeaker.toLowerCase();
    const isHeader = IGNORED_NAME_PREFIXES.some((p) => lowerClean.startsWith(p) || lowerClean === p);
    if (!isHeader && cleanSpeaker.length >= 2 && cleanSpeaker.length <= 32 && !/^\d+$/.test(cleanSpeaker)) {
      blocks.push({ name: cleanSpeaker, text: m[2].trim() });
    }
  }
}
console.log('Matched blocks count:', blocks.length);
console.log('Blocks:', blocks);
