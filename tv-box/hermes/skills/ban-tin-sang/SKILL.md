---
name: ban-tin-sang
description: Viết "Bản tin sáng" hằng ngày cho nhóm bằng tiếng Việt — 4 mục tin 24 giờ qua, định dạng Slack mrkdwn, có nguồn cho từng tin.
---

Viết "Bản tin sáng" cho nhóm, bằng tiếng Việt.

QUY TRÌNH:
1. Xác định ngày hôm nay (giờ Việt Nam, UTC+7). Gọi web_search nhiều lần, mỗi mục bên dưới ít nhất 2 truy vấn khác nhau. web_search KHÔNG có bộ lọc thời gian, nên LUÔN đưa ngày hoặc tháng hiện tại vào truy vấn (ví dụ "AI news September 24 2026", "tin kinh tế Việt Nam 24/9/2026").
2. Dùng web_extract để mở các bài quan trọng và lấy số liệu cụ thể. KHÔNG viết chi tiết nào mà bạn chưa đọc được từ nguồn. Loại mọi bài đăng quá 24 giờ trước — kiểm tra ngày đăng trong nội dung bài.
3. Bỏ qua tin đồn chưa có nguồn sơ cấp. Nếu có tin lan truyền nhưng không xác minh được, ghi vào phần Ghi chú cuối bản tin.

BỐ CỤC (4 mục, mỗi mục 3-5 gạch đầu dòng, tin mới nhất trước):
*Công nghệ & AI*
*Kỹ thuật phần mềm*
*Tin thế giới & kinh doanh*
*Việt Nam*

MỖI GẠCH ĐẦU DÒNG:
- Mở đầu bằng một câu tóm tắt in đậm, kết thúc bằng dấu chấm.
- Sau đó 1-2 câu chi tiết, ưu tiên con số cụ thể (số tiền, phần trăm, ngày, quy mô).
- Kết thúc bằng nguồn dạng link.

ĐỊNH DẠNG SLACK — bắt buộc, đây KHÔNG phải markdown thường:
- In đậm dùng MỘT dấu sao: *chữ đậm*. Tuyệt đối không dùng hai dấu sao.
- Link dùng dạng <https://url|Tên nguồn, dd/MM>. Tuyệt đối không dùng [text](url).
- Gạch đầu dòng bắt đầu bằng "• ".
- Tiêu đề mục viết trên một dòng riêng, in đậm.

Dòng đầu tiên của bản tin: *Bản tin sáng — <thứ>, <dd/MM/yyyy>* và ghi rõ mốc thời gian dữ liệu.
Nếu một mục không có tin đáng kể trong 24 giờ, ghi một dòng in nghiêng _không có tin nổi bật_ thay vì bịa tin.
Kết thúc bằng dòng Ghi chú nếu có tin bị loại vì chưa xác minh.

GIỚI HẠN BẮT BUỘC:
- CHỈ web_extract các URL bài viết cụ thể. TUYỆT ĐỐI không mở trang chủ như reuters.com, techcrunch.com, bloomberg.com, vnexpress.net trần.
- Tối đa 8 URL web_extract cho toàn bộ bản tin (mỗi lần gọi tối đa 5 URL).
- Nếu một truy vấn không ra kết quả, đổi từ khoá; không lặp lại quá 2 truy vấn tương tự.
- Nếu sau 3 vòng tìm kiếm vẫn thiếu dữ liệu cho một mục, ghi _không có tin nổi bật_ và đi tiếp.
- Chỉ trả về nội dung bản tin — không có lời dẫn kiểu "Dựa trên kết quả tìm kiếm…", không để trống chỗ giữ chỗ như "Tên nguồn".

QUY TẮC IN ĐẬM (bắt buộc, lần trước làm sai):
- ĐÚNG:  *Bản tin sáng — Thứ Năm, 13/08/2026*
- SAI:   * Bản tin sáng — Thứ Năm, 13/08/2026 *
  Dấu sao phải DÍNH LIỀN ký tự đầu và ký tự cuối, không có dấu cách xen giữa.

ĐA DẠNG NGUỒN (bắt buộc):
- Mỗi gạch đầu dòng phải đến từ một URL KHÁC NHAU. Không lấy nhiều gạch đầu dòng từ cùng một bài viết.
- Mục *Công nghệ & AI* và *Tin thế giới & kinh doanh*: tìm bằng TIẾNG ANH, ưu tiên nguồn quốc tế (Reuters, TechCrunch, The Verge, Bloomberg, BleepingComputer).
- Mục *Kỹ thuật phần mềm*: tin về release, CVE, sự cố bảo mật, công cụ lập trình. Không đưa tin tuyển sinh hay cuộc thi sinh viên.
- Mục *Việt Nam*: tìm bằng TIẾNG VIỆT, nguồn trong nước (VnExpress, CafeF, Báo Chính phủ, Tuổi Trẻ, Thanh Niên).
