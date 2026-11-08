"""
Script Generator & Pipeline Engine cho Video dài chuẩn 3-5 phút (500 - 800 từ)
Hỗ trợ sinh đa dạng kịch bản có chiều sâu theo chuẩn cấu trúc:
1. Hook (0:00 - 0:15)
2. Bối cảnh & Vấn đề (0:15 - 0:45)
3. Luận điểm 1 (0:45 - 1:30)
4. Luận điểm 2 (1:30 - 2:15)
5. Luận điểm 3 (2:15 - 3:00)
6. Góc nhìn phản biện / Đảo chiều (3:00 - 3:45)
7. Đúc kết & Bài học hành động (3:45 - 4:30+)
"""

import json
from pathlib import Path

# Kho kịch bản chuyên sâu 3-5 phút cho các draft
PRESET_LONG_SCRIPTS = {
    "lich_su_loai_nguoi": [
        {
            "id": "draft_01",
            "style_name": "Hành Trình Sử Thi — 70.000 Năm Thống Trị Trái Đất",
            "theme": "gold",
            "bgm_type": "cinematic_epic",
            "title": "HÀNH TRÌNH 70.000 NĂM CỦA LOÀI NGƯỜI",
            "target_duration_sec": 210,  # ~3.5 phút
            "scenes": [
                {
                    "title": "Khởi đầu yếu ớt",
                    "spoken": "Cách đây 70 nghìn năm, tổ tiên chúng ta, loài Homo sapiens, chỉ là một nhánh động vật nhỏ bé, không có nanh vuốt sắc nhọn, không có sức mạnh cơ bắp vượt trội và liên tục phải trốn chạy các loài săn mồi to lớn trên thảo nguyên châu Phi. Chúng ta không có bất kỳ dấu hiệu nào cho thấy sẽ trở thành sinh vật thống trị hành tinh này.",
                    "keywords": ["Tổ tiên loài người", "Thảo nguyên Châu Phi", "Sinh vật yếu ớt"]
                },
                {
                    "title": "Cách mạng Nhận thức",
                    "spoken": "Thế nhưng, một đột biến di truyền kỳ diệu đã khai sinh ra Cuộc cách mạng Nhận thức. Con người bắt đầu có khả năng sáng tạo ngôn ngữ phức tạp. Điều đặc biệt không phải là chúng ta có thể nói về một con hổ đang rình rập, mà là chúng ta có thể kể cho nhau nghe những câu chuyện về những thứ không hề tồn tại trong thế giới vật lý: thần linh, linh hồn và những điều thiêng liêng.",
                    "keywords": ["Cách mạng Nhận thức", "Sức mạnh ngôn ngữ", "Trật tự tưởng tượng"]
                },
                {
                    "title": "Sức mạnh của Trật tự Tưởng tượng",
                    "spoken": "Chính năng lực tin vào những điều tưởng tượng đã giúp loài người giải quyết được bài toán lớn nhất của muôn loài: hợp tác quy mô lớn. Một bầy tinh tinh chỉ có thể gắn kết tối đa 50 cá thể dựa trên quan hệ quen biết. Nhưng hàng vạn con người xa lạ có thể cùng nhau xây dựng kim tự tháp, cùng ra trận hay cùng giao thương, chỉ vì họ cùng tin vào một vị thần, một vị vua hoặc một lời thề chung.",
                    "keywords": ["Hợp tác bầy đàn", "Quy mô không giới hạn", "Niềm tin tập thể"]
                },
                {
                    "title": "Cuộc cách mạng Nông nghiệp",
                    "spoken": "Mười hai nghìn năm trước, Cách mạng Nông nghiệp bùng nổ khi con người bắt đầu thuần hóa lúa mì, lúa gạo và gia súc. Nhưng giáo sư Yuval Noah Harari đã gọi đây là cú lừa vĩ đại nhất lịch sử. Thay vì sống thảnh thơi với săn bắt hái lượm, người nông dân phải làm việc quần quật từ bình minh đến hoàng hôn, tích lũy của cải và tạo ra bất bình đẳng giai cấp, chiến tranh lãnh thổ và dịch bệnh lan rộng.",
                    "keywords": ["Cách mạng Nông nghiệp", "Cú lừa lịch sử", "Định cư & Đế chế"]
                },
                {
                    "title": "Khai phóng Khoa học & Công nghệ",
                    "spoken": "Năm trăm năm trước, con người dũng cảm thừa nhận sự dốt nát của mình để bắt đầu cuộc Cách mạng Khoa học. Từ động cơ hơi nước, điện năng, internet cho đến kỷ nguyên thám hiểm vũ trụ và trí tuệ nhân tạo ngày nay, quyền năng của con người đã vượt xa mọi giới hạn sinh học bình thường.",
                    "keywords": ["Cách mạng Khoa học", "Động cơ hơi nước", "Kỷ nguyên số & AI"]
                },
                {
                    "title": "Lời cảnh tỉnh cho tương lai",
                    "spoken": "Ngày nay, chúng ta đứng trước ngưỡng cửa nâng cấp chính bộ gen của mình và tiến hóa thành những sinh mệnh bán cơ khí. Chúng ta kiểm soát gần như mọi nguồn lực trên Trái Đất, nhưng một câu hỏi nhức nhối vẫn còn đó: Liệu sau tất cả những vinh quang ấy, chúng ta có thực sự hạnh phúc hơn tổ tiên của mình không?",
                    "keywords": ["Tương lai nhân loại", "Hạnh phúc đích thực", "Trí tuệ nhân tạo"]
                }
            ]
        },
        {
            "id": "draft_02",
            "style_name": "Phân Tích Chuyên Sâu — 3 Cuộc Cách Mạng Định Hình Xã Hội",
            "theme": "dark",
            "bgm_type": "documentary_thoughtful",
            "title": "3 CỘT MỐC ĐỊNH HÌNH TOÀN BỘ NHÂN LOẠI",
            "target_duration_sec": 200,
            "scenes": [
                {
                    "title": "Đặt vấn đề",
                    "spoken": "Tại sao con người lại có thể xây dựng những đô thị hàng chục triệu dân, trong khi các loài linh trưởng gần gũi nhất với chúng ta vẫn chỉ sống thành từng đàn nhỏ trong rừng rậm? Câu trả lời nằm ở ba bước nhảy vọt lịch sử mà bất kỳ ai muốn hiểu bản chất xã hội hiện đại đều phải nắm rõ.",
                    "keywords": ["Bản chất xã hội", "Đô thị hiện đại", "3 bước nhảy vọt"]
                },
                {
                    "title": "Bước nhảy 1: Trí tưởng tượng liên kết",
                    "spoken": "Cột mốc thứ nhất diễn ra vào khoảng 70 nghìn năm trước. Cách mạng Nhận thức tạo ra khái niệm về tiền tệ và luật pháp. Tiền bạc không phải là giấy hay kim loại, tiền bạc là một tôn giáo của sự tin tưởng. Khi tất cả mọi người cùng tin một tờ giấy có giá trị, dòng chảy kinh tế toàn cầu được hình thành.",
                    "keywords": ["Khái niệm Tiền tệ", "Sự tin tưởng tập thể", "Kinh tế toàn cầu"]
                },
                {
                    "title": "Bước nhảy 2: Định cư và Thặng dư lương thực",
                    "spoken": "Cột mốc thứ hai là Cách mạng Nông nghiệp. Việc tạo ra thặng dư lương thực lần đầu tiên cho phép một bộ phận xã hội không cần trực tiếp làm ruộng mà có thể trở thành triết gia, nhà toán học, kỹ sư và binh lính. Nền văn minh chữ viết và các nhà nước cổ đại đã ra đời từ chính nguồn thặng dư này.",
                    "keywords": ["Thặng dư lương thực", "Khai sinh chữ viết", "Nhà nước cổ đại"]
                },
                {
                    "title": "Bước nhảy 3: Phương pháp thực nghiệm",
                    "spoken": "Cột mốc thứ ba là Cách mạng Khoa học. Thay vì tin mù quáng vào các giáo điều cổ xưa, con người đo lường thế giới bằng toán học và thực nghiệm. Sự kết hợp giữa chủ nghĩa tư bản, công nghệ và khoa học đã nhân cấp sức mạnh sản xuất lên hàng triệu lần chỉ trong vài thế kỷ ngắn ngủi.",
                    "keywords": ["Phương pháp thực nghiệm", "Toán học & Khoa học", "Bùng nổ sản xuất"]
                },
                {
                    "title": "Bài học cốt lõi",
                    "spoken": "Nhìn lại toàn bộ hành trình, bạn sẽ nhận ra một chân lý: Bất kỳ tổ chức, doanh nghiệp hay xã hội nào thành công đều phải làm chủ được hai thứ: một câu chuyện truyền cảm hứng để tập hợp niềm tin, và một hệ thống công nghệ để biến câu chuyện đó thành hiện thực.",
                    "keywords": ["Niềm tin chung", "Công nghệ thực thi", "Bài học lãnh đạo"]
                }
            ]
        },
        {
            "id": "draft_03",
            "style_name": "Phản Biện Sắc Bén — Mặt Tối Của Sự Tiến Hóa",
            "theme": "emerald",
            "bgm_type": "deep_reflective",
            "title": "MẶT TỐI CỦA SỰ THỐNG TRỊ NHÂN LOẠI",
            "target_duration_sec": 190,
            "scenes": [
                {
                    "title": "Góc nhìn ngược chiều",
                    "spoken": "Chúng ta thường tự hào về sự tiến bộ không ngừng của nền văn minh. Nhưng nếu nhìn từ lăng kính của tự nhiên và sinh thái, lịch sử loài người lại là chuỗi ngày tàn phá khốc liệt nhất đối với hành tinh này.",
                    "keywords": ["Ảo tưởng tiến bộ", "Cân bằng sinh thái", "Góc nhìn phản biện"]
                },
                {
                    "title": "Đại tuyệt chủng của các loài thú lớn",
                    "spoken": "Ngay từ khi những người Homo sapiens đầu tiên đặt chân lên châu Úc và châu Mỹ, hơn 70% các loài động vật có vú khổng lồ đã tuyệt chủng vĩnh viễn. Con người đã trở thành loài động vật nguy hiểm nhất trên cạn trước cả khi phát minh ra bánh xe hay công cụ bằng kim loại.",
                    "keywords": ["Đại tuyệt chủng kỷ Pleistocene", "Hệ sinh thái sụp đổ", "Kẻ săn mồi tối thượng"]
                },
                {
                    "title": "Bẫy tiện nghi hiện đại",
                    "spoken": "Công nghệ giúp cuộc sống tiện nghi hơn, nhưng đồng thời trói buộc chúng ta vào những áp lực vô hình: báo cáo công việc, nợ nần tài chính và sự cô đơn giữa những khối bê tông khổng lồ. Chúng ta có thể kết nối với toàn cầu qua màn hình điện thoại, nhưng lại mất dần sự kết nối sâu sắc với tự nhiên và chính tâm hồn mình.",
                    "keywords": ["Bẫy tiện nghi", "Áp lực công việc", "Mất kết nối tự nhiên"]
                },
                {
                    "title": "Lời nhắc nhở cho hiện tại",
                    "spoken": "Lịch sử không chỉ là để chiêm ngưỡng những thành tựu rực rỡ, mà là tấm gương để nhắc nhở chúng ta sống có trách nhiệm hơn. Tiến hóa thực sự không phải là thống trị vạn vật, mà là học cách sống hòa hợp và tìm thấy bình yên bên trong chính mình.",
                    "keywords": ["Trách nhiệm thế hệ", "Sống hòa hợp", "Bình yên nội tại"]
                }
            ]
        }
    ]
}
