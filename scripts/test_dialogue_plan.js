const fs = require('fs');

const regex = /^([A-ZÀ-ỸĐ0-9][A-ZÀ-ỸĐ0-9 ._\-()]{1,42}):\s*(.*)$/i;
const testLines = [
  '**TẬP 2: TỪ NGƯỜI LÍNH THẤT BẠI ĐẾN KẺ KÍCH ĐỘNG CHÍNH TRỊ**',
  'TẬP 2: TỪ NGƯỜI LÍNH THẤT BẠI',
  'BƯỚC 1: TÌM ĐƯỜNG',
  'HẾT: CÂU CHUYỆN',
  'Lưu ý: Không được quên'
];

testLines.forEach(line => {
  const clean = line.replace(/^[*#_~`“”"]+|[*#_~`“”"]+$/g, '').trim();
  const m = clean.match(regex);
  console.log(line, '->', clean, 'match:', m ? m[1] : null);
});
