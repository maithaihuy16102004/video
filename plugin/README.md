# Plugin — Content Studio

Thư mục chứa **plugin DSH** đóng gói toàn bộ workspace `D:\Agent`.

## Cấu trúc

```
plugin/
└── content-studio/
    ├── SKILL.md           ← định nghĩa skill cho DSH agent
    ├── README.md          ← hướng dẫn đầy đủ
    ├── content_studio.py  ← tìm workspace + sys.path
    ├── bootstrap.py       ← entrypoint cho script con
    ├── __main__.py        ← CLI thống nhất
    ├── install.ps1        ← cài vào %USERPROFILE%\.dsh\skills
    ├── sync.ps1           ← đồng bộ code (chế độ copy)
    ├── test_plugin.py     ← 9 test tự kiểm tra
    ├── .cs-root           ← đường dẫn workspace gốc
    ├── modules/           ← bản sao portable (nếu sync)
    ├── motion-fx/         ← motion graphic
    └── examples/          ← draft mẫu
```

## Cài nhanh

```powershell
powershell -ExecutionPolicy Bypass -File plugin\content-studio\install.ps1
```

## Kiểm tra

```powershell
cd plugin\content-studio
python test_plugin.py
```

Sau đó trong phiên DSH mới, nói:

> "Dùng content-studio làm video về ..."

Xem chi tiết tại [`content-studio/README.md`](content-studio/README.md).
