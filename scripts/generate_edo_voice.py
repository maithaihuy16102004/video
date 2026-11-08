import os
import sys
from pathlib import Path

ROOT = Path(".").resolve()
sys.path.insert(0, str(ROOT / "pipeline"))

import studio_api

out_dir = ROOT / "output" / "edo_courier_audio"
out_dir.mkdir(parents=True, exist_ok=True)

segments = [
    {
        "speaker": "Haru",
        "character": "haru",
        "voice": "vieneu-Đức Trí",
        "text": "Tôi tên Haru. Năm ấy, tôi làm nghề đưa thư ở Edo. Một công việc rất đơn giản: nhận thư, chạy thật nhanh, và cố gắng không chết trên đường. Cho đến một buổi chiều, ông chủ đưa cho tôi một phong thư được bọc trong giấy dầu.",
        "rate": "+0%", "pitch": "+0Hz"
    },
    {
        "speaker": "Ông chủ",
        "character": "ong_chu",
        "voice": "vieneu-Mạnh Dũng",
        "text": "Đưa nó tới nhà Aiko trước khi chuông tối vang lên. Và nhớ kỹ... tuyệt đối không được để ướt!",
        "rate": "-3%", "pitch": "-4Hz"
    },
    {
        "speaker": "Haru",
        "character": "haru",
        "voice": "vieneu-Đức Trí",
        "text": "Tôi nhìn phong thư. Rồi nhìn bầu trời. Một giọt mưa rơi trúng mũi tôi. Tuyệt vời. Đúng là ngày đẹp trời để bắt đầu một thảm họa.",
        "rate": "+0%", "pitch": "+0Hz"
    },
    {
        "speaker": "Haru",
        "character": "haru",
        "voice": "vieneu-Đức Trí",
        "text": "Chưa đầy năm phút sau, cả con phố biến thành một dòng sông nhỏ. Tôi chạy qua những cửa hàng gỗ, né một chiếc xe kéo, rồi suýt đâm đầu vào người bán cá.",
        "rate": "+2%", "pitch": "+0Hz"
    },
    {
        "speaker": "Người bán cá",
        "character": "ban_ca",
        "voice": "vieneu-Thái Sơn",
        "text": "Nhìn đường chứ, nhóc!",
        "rate": "+4%", "pitch": "+3Hz"
    },
    {
        "speaker": "Haru",
        "character": "haru",
        "voice": "vieneu-Đức Trí",
        "text": "Tôi cúi đầu xin lỗi, nhưng chân vẫn chạy. Bởi vì trong tay tôi là một bức thư quan trọng. Còn trong đầu tôi lúc ấy chỉ có một suy nghĩ: Nếu thư ướt, ông chủ sẽ biến tôi thành cá khô!",
        "rate": "+0%", "pitch": "+0Hz"
    },
    {
        "speaker": "Haru",
        "character": "haru",
        "voice": "vieneu-Đức Trí",
        "text": "Đến cây cầu bắc qua con kênh, tôi nhận ra một vấn đề. Một tấm ván đã gãy. Nước mưa chảy qua mặt cầu. Và bên dưới là dòng nước đen ngòm. Tôi hít sâu, kẹp phong thư vào trong áo, rồi bước lên. Một bước. Hai bước. RẮC! Tấm ván dưới chân tôi bật tung. Tôi ngã nhào, một tay bám vào lan can, tay còn lại ôm chặt phong thư. Thật kỳ lạ. Giữa lúc mạng sống treo trên một thanh gỗ mục, điều tôi lo nhất vẫn là: Bức thư có bị ướt không?",
        "rate": "+1%", "pitch": "+0Hz"
    },
    {
        "speaker": "Haru",
        "character": "haru",
        "voice": "vieneu-Đức Trí",
        "text": "Khi tôi tới nơi, trời đã tối hẳn. Tôi đứng trước một ngôi nhà gỗ, toàn thân ướt sũng, tóc dính bết vào trán. Một cô gái mở cửa.",
        "rate": "-1%", "pitch": "+0Hz"
    },
    {
        "speaker": "Aiko",
        "character": "aiko",
        "voice": "vieneu-Trúc Ly",
        "text": "Anh là người đưa thư?",
        "rate": "-2%", "pitch": "+2Hz"
    },
    {
        "speaker": "Haru",
        "character": "haru",
        "voice": "vieneu-Đức Trí",
        "text": "Vâng. Và tôi xin thông báo... bức thư vẫn khô. Tôi đưa phong thư cho cô ấy bằng cả hai tay, như thể đang trao một báu vật. Aiko mở thư. Cô đọc rất nhanh. Rồi đột nhiên bật cười.",
        "rate": "+0%", "pitch": "+0Hz"
    },
    {
        "speaker": "Haru",
        "character": "haru",
        "voice": "vieneu-Đức Trí",
        "text": "Tôi đứng chết lặng. Tôi đã chạy xuyên cơn bão, suýt rơi xuống kênh, và mất gần hết lòng tự trọng. Vậy mà cô ấy... cười?",
        "rate": "-2%", "pitch": "+0Hz"
    },
    {
        "speaker": "Aiko",
        "character": "aiko",
        "voice": "vieneu-Trúc Ly",
        "text": "Anh có biết trong thư viết gì không?",
        "rate": "-1%", "pitch": "+2Hz"
    },
    {
        "speaker": "Haru",
        "character": "haru",
        "voice": "vieneu-Đức Trí",
        "text": "Tôi chỉ biết nó không được phép ướt.",
        "rate": "+0%", "pitch": "-1Hz"
    },
    {
        "speaker": "Aiko",
        "character": "aiko",
        "voice": "vieneu-Trúc Ly",
        "text": "Aiko, nhớ mang ô. Chiều nay có thể mưa.",
        "rate": "-2%", "pitch": "+1Hz"
    },
    {
        "speaker": "Haru",
        "character": "haru",
        "voice": "vieneu-Đức Trí",
        "text": "Tôi nhìn dòng chữ. Nhìn cơn mưa phía sau lưng. Rồi nhìn đôi dép của mình... một chiếc đã mất từ lúc qua cầu. Hôm ấy, tôi học được một bài học vô cùng quý giá. Đôi khi, thứ quan trọng nhất trong một bức thư... Là biết nó viết cái quái gì trước khi mang đi!",
        "rate": "-1%", "pitch": "+0Hz"
    }
]

print(f"Generating dialogue track for {len(segments)} segments...")
wav_path, vtt_path = studio_api.make_dialogue_voice(segments, out_dir)
duration = studio_api.voice_duration(wav_path)
print(f"SUCCESS! Voice WAV: {wav_path}")
print(f"Duration: {duration:.2f} seconds ({duration/60:.1f} minutes)")
print(f"Captions: {vtt_path}")
