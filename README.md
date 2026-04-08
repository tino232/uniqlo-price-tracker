# Uniqlo Price Tracker 🛍️

Tự động theo dõi giá và tình trạng hàng từ Uniqlo VN, gửi thông báo qua Telegram.

## Tính năng
- ✅ Track giá mỗi 3 ngày
- 🏷️ Alert ngay khi có/hết sale (giá gạch)
- ❌ Alert ngay khi hết hàng / còn hàng trở lại

## Thêm / Xoá URL

Chỉnh file `urls.json`:

```json
{
  "urls": [
    "https://www.uniqlo.com/vn/vi/products/...",
    "https://www.uniqlo.com/vn/vi/products/..."
  ]
}
```

Commit & push là xong. Lần chạy tiếp theo sẽ áp dụng danh sách mới.

## Chạy thủ công

Vào tab **Actions** → chọn workflow → **Run workflow**.
